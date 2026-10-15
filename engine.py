"""engine.py - domain models, memory engine, task engine, scheduler, application service.

The chain implemented here:

    Topic -> LearningEvent -> MemoryState -> Review Task -> Task Pool
          -> Availability -> Dynamic Scheduler -> StudySession -> Actual Result

Sections
--------
 0. Enums and configuration (every tunable number lives in EngineConfig)
 A. Domain models (+ generic row <-> dataclass codec)
 B. Memory engine   (answers: "when should this topic be reviewed?")
 C. Task engine     (task factories, occurrence generation, splitting)
 D. Scheduler       (answers: "when in the student's real life should it happen?")
 E. Application service (the only thing ui.py talks to; uses database.py for all I/O)

NOTE ON PARAMETERS: all numeric parameters are *initial experimental parameters*.
None of them is claimed to be scientifically validated or optimal.
"""
from __future__ import annotations

import dataclasses
import json
import math
import types
import typing
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Mapping, Sequence

from database import Database


# =========================================================================== #
# 0. ENUMS AND CONFIGURATION
# =========================================================================== #

class TaskClass(str, Enum):
    REVIEW = "REVIEW"
    DEADLINE_TASK = "DEADLINE_TASK"
    RECURRING_TASK = "RECURRING_TASK"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    MISSED = "MISSED"          # recurring occurrence whose window expired


class ReviewSource(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"


class AvailabilityType(str, Enum):
    PRIMARY = "PRIMARY"
    RESERVE = "RESERVE"
    UNAVAILABLE = "UNAVAILABLE"


class SlotKind(str, Enum):
    PRIMARY = "PRIMARY"
    BUFFER = "BUFFER"          # last part of PRIMARY time, protected for overruns
    RESERVE = "RESERVE"


class SessionStatus(str, Enum):
    PLANNED = "PLANNED"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    SKIPPED = "SKIPPED"


class MemoryPhase(str, Enum):
    NEW = "NEW"                # seen in class, never actively recalled yet
    REVIEW = "REVIEW"
    RELEARNING = "RELEARNING"  # last recall attempt failed


class RecurrenceKind(str, Enum):
    DAILY = "DAILY"
    WEEKDAYS = "WEEKDAYS"              # fixed weekdays, e.g. Mon/Wed/Fri
    TIMES_PER_WEEK = "TIMES_PER_WEEK"  # N times a week, scheduler picks the days


class UnscheduledReason(str, Enum):
    NO_AVAILABILITY = "NO_AVAILABILITY"
    INSUFFICIENT_CAPACITY = "INSUFFICIENT_CAPACITY"
    NO_CONTIGUOUS_SLOT = "NO_CONTIGUOUS_SLOT"
    WINDOW_EXPIRED = "WINDOW_EXPIRED"
    OUTSIDE_HORIZON = "OUTSIDE_HORIZON"


@dataclass(frozen=True)
class MemoryConfig:
    """Initial EXPERIMENTAL memory-model parameters (not scientifically validated)."""
    # recall score blending
    objective_weight: float = 0.75
    subjective_weight: float = 0.25
    rating_min: int = 1
    rating_max: int = 10
    # (upper bound exclusive, multiplier); Q >= last bound -> top_multiplier
    multiplier_bands: tuple[tuple[float, float], ...] = (
        (0.40, 0.50), (0.60, 0.80), (0.80, 1.20), (0.90, 1.60))
    top_multiplier: float = 2.00
    # stability
    stability_min_days: float = 1.0
    stability_max_days: float = 180.0
    initial_stability_days: float = 3.0
    # difficulty
    initial_difficulty: float = 0.5
    difficulty_step: float = 0.10
    difficulty_neutral_q: float = 0.5
    difficulty_factor_base: float = 1.10
    difficulty_factor_slope: float = 0.20
    use_updated_difficulty_for_stability: bool = False
    # forgetting model R(t) = 2^(-t/S)
    target_recall: float = 0.85
    min_interval_days: int = 1
    relearning_interval_days: int = 1
    failure_threshold_q: float = 0.40
    # review window around the ideal date (a review date is NOT a hard deadline)
    window_days_before: int = 1
    window_days_after: int = 1
    # review task defaults
    review_priority: int = 6
    review_minutes_first_topic: int = 30
    review_minutes_extra_topic: int = 15
    urgency_base: float = 5.0
    urgency_difficulty_gain: float = 3.0
    urgency_relearning_bonus: float = 2.0

    def __post_init__(self) -> None:
        if self.objective_weight < 0 or self.subjective_weight < 0 or \
                self.objective_weight + self.subjective_weight <= 0:
            raise ValueError("recall weights must be non-negative and not both zero")
        if not 0.0 < self.target_recall < 1.0:
            raise ValueError("target_recall must be in (0, 1)")
        if self.stability_min_days <= 0 or self.stability_max_days < self.stability_min_days:
            raise ValueError("invalid stability bounds")
        if self.rating_max <= self.rating_min:
            raise ValueError("rating_max must exceed rating_min")
        bounds = [b for b, _ in self.multiplier_bands]
        if bounds != sorted(bounds):
            raise ValueError("multiplier_bands must be ascending")


@dataclass(frozen=True)
class TaskConfig:
    default_minimum_session: int = 20     # for splittable tasks without an explicit minimum
    max_priority: int = 10
    min_priority: int = 1
    occurrence_horizon_days: int = 21     # how far ahead recurring occurrences are materialised


@dataclass(frozen=True)
class SchedulerConfig:
    """Initial EXPERIMENTAL scheduler parameters; all weights are tunable."""
    horizon_days: int = 14
    # buffer: share of each day's PRIMARY capacity kept free (taken from the end of the day)
    buffer_fraction: float = 0.20
    max_session_minutes: int = 120        # applies to splittable tasks only
    # cost per minute of using a slot kind
    slot_cost_primary: float = 0.0
    slot_cost_buffer: float = 1.0
    slot_cost_reserve: float = 2.0
    reserve_eligible_classes: tuple[TaskClass, ...] = (TaskClass.DEADLINE_TASK, TaskClass.RECURRING_TASK)
    buffer_pressure_threshold: float = 0.6   # buffer may only be used by deadline items above this pressure
    # ordering score weights (soft optimisation)
    w_priority: float = 1.0
    w_deadline: float = 2.5
    w_review: float = 1.5
    w_exam: float = 1.0
    w_routine: float = 0.8
    w_delay_cost: float = 0.5
    overdue_pressure: float = 1.5
    review_lateness_gain: float = 0.1
    review_lateness_cap: float = 0.5
    exam_horizon_days: int = 14
    exam_pull_forward: bool = True        # ideal review date is pulled to exam_date - 1 for exam topics
    exam_pull_forward_days: int = 1
    # placement cost (per minute) - time dimension
    review_early_cost_per_day: float = 0.3
    review_late_cost_per_day: float = 0.5
    review_outside_window_penalty: float = 1.0
    review_outside_window_per_day: float = 0.5
    review_urgency_base: float = 0.5      # factor = base + urgency/10
    review_max_early_days: int = 2        # never plan a review earlier than window start - this
    review_day_cap_fraction: float = 0.5  # max share of a day's PRIMARY capacity used by reviews
    deadline_risk_weight: float = 1.0
    overdue_asap_cost_per_day: float = 0.1
    recurring_distance_cost_per_day: float = 0.3
    load_balance_weight: float = 0.4
    split_penalty: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 <= self.buffer_fraction < 1.0:
            raise ValueError("buffer_fraction must be in [0, 1)")
        if self.horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")


@dataclass(frozen=True)
class EngineConfig:
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    def with_overrides(self, overrides: Mapping[str, Mapping[str, Any]]) -> "EngineConfig":
        """``{"memory": {"target_recall": 0.9}, "scheduler": {...}}`` -> new config."""
        parts = {"memory": self.memory, "task": self.task, "scheduler": self.scheduler}
        for section, values in overrides.items():
            if section not in parts:
                raise ValueError(f"Unknown config section: {section}")
            parts[section] = replace(parts[section], **values)
        return EngineConfig(**parts)


DEFAULT_CONFIG = EngineConfig()
MINUTES_PER_DAY = 24 * 60


# =========================================================================== #
# A. DOMAIN MODELS
# =========================================================================== #

def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


@dataclass(frozen=True)
class RecurringRule:
    kind: RecurrenceKind
    weekdays: tuple[int, ...] = ()        # 0 = Monday ... 6 = Sunday (WEEKDAYS)
    times_per_week: int = 0               # TIMES_PER_WEEK
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        if self.kind is RecurrenceKind.WEEKDAYS and not self.weekdays:
            raise ValueError("WEEKDAYS rule needs at least one weekday")
        if any(not 0 <= d <= 6 for d in self.weekdays):
            raise ValueError("weekday must be in 0..6")
        if self.kind is RecurrenceKind.TIMES_PER_WEEK and not 1 <= self.times_per_week <= 7:
            raise ValueError("times_per_week must be in 1..7")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date before start_date")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "weekdays": list(self.weekdays),
                "times_per_week": self.times_per_week,
                "start_date": self.start_date.isoformat() if self.start_date else None,
                "end_date": self.end_date.isoformat() if self.end_date else None}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "RecurringRule":
        return RecurringRule(
            kind=RecurrenceKind(d["kind"]), weekdays=tuple(d.get("weekdays", ())),
            times_per_week=int(d.get("times_per_week", 0)),
            start_date=date.fromisoformat(d["start_date"]) if d.get("start_date") else None,
            end_date=date.fromisoformat(d["end_date"]) if d.get("end_date") else None)

    def describe(self) -> str:
        names = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
        if self.kind is RecurrenceKind.DAILY:
            return "Her gün"
        if self.kind is RecurrenceKind.WEEKDAYS:
            return "Her " + "/".join(names[d] for d in self.weekdays)
        return f"Haftada {self.times_per_week} gün"


@dataclass
class Student:
    name: str
    id: int | None = None
    created_at: datetime = field(default_factory=_now)


@dataclass
class Subject:
    name: str
    id: int | None = None
    student_id: int = 1
    color: str = "#4F7CAC"
    created_at: datetime = field(default_factory=_now)


@dataclass
class Unit:
    name: str
    subject_id: int
    id: int | None = None
    order_no: int = 1
    start_date: date | None = None
    end_date: date | None = None
    created_at: datetime = field(default_factory=_now)


@dataclass
class Topic:
    name: str
    subject_id: int
    id: int | None = None
    unit_id: int | None = None
    notes: str = ""
    created_at: datetime = field(default_factory=_now)


@dataclass
class LearningEvent:
    topic_id: int
    event_date: date
    id: int | None = None
    period_start: int | None = None      # school period numbers, e.g. 1-2
    period_end: int | None = None
    notes: str = ""
    created_at: datetime = field(default_factory=_now)


@dataclass
class MemoryState:
    topic_id: int
    stability_days: float
    difficulty: float
    phase: MemoryPhase
    last_review_date: date
    next_review_date: date               # IDEAL review date (not a hard deadline)
    review_count: int = 0
    lapse_count: int = 0
    last_objective_score: float | None = None
    last_subjective_score: float | None = None
    last_combined_score: float | None = None
    updated_at: datetime = field(default_factory=_now)


@dataclass
class Exam:
    title: str
    exam_date: date
    id: int | None = None
    student_id: int = 1
    subject_id: int | None = None
    notes: str = ""
    topic_ids: list[int] = field(default_factory=list)   # not a column (exam_topic_links)


@dataclass
class Task:
    title: str
    task_class: TaskClass
    duration: int
    id: int | None = None
    student_id: int = 1
    remaining_duration: int | None = None
    priority: int = 5
    deadline: date | None = None
    ideal_date: date | None = None
    earliest_date: date | None = None
    latest_date: date | None = None
    splittable: bool = False
    minimum_session: int = 0
    recurring_rule: RecurringRule | None = None
    tags: list[str] = field(default_factory=list)
    review_source: ReviewSource | None = None
    status: TaskStatus = TaskStatus.PENDING
    urgency: float = 5.0
    delay_cost: float = 0.0
    exam_id: int | None = None
    notes: str = ""
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    topic_ids: list[int] = field(default_factory=list)   # not a column (task_topic_links)

    def __post_init__(self) -> None:
        if self.remaining_duration is None:
            self.remaining_duration = self.duration

    def validate(self, cfg: TaskConfig = TaskConfig()) -> None:
        if not self.title.strip():
            raise ValueError("title is required")
        if self.duration <= 0:
            raise ValueError("duration must be > 0 minutes")
        if self.remaining_duration is None or self.remaining_duration < 0:
            raise ValueError("remaining_duration must be >= 0")
        if not cfg.min_priority <= self.priority <= cfg.max_priority:
            raise ValueError(f"priority must be in {cfg.min_priority}..{cfg.max_priority}")
        if self.splittable and not 0 < self.minimum_session <= self.duration:
            raise ValueError("minimum_session must be in 1..duration for splittable tasks")
        if self.task_class is TaskClass.DEADLINE_TASK and self.deadline is None:
            raise ValueError("deadline task needs a deadline")
        if self.task_class is TaskClass.RECURRING_TASK and self.recurring_rule is None:
            raise ValueError("recurring task needs a recurring_rule")
        if self.task_class is TaskClass.REVIEW and self.ideal_date is None:
            raise ValueError("review task needs an ideal_date")

    def is_overdue(self, today: date) -> bool:
        if self.status is not TaskStatus.PENDING:
            return False
        if self.task_class is TaskClass.DEADLINE_TASK:
            return self.deadline is not None and self.deadline < today
        if self.task_class is TaskClass.REVIEW:
            return self.latest_date is not None and self.latest_date < today
        return False


@dataclass
class TaskOccurrence:
    task_id: int
    occurrence_date: date
    duration: int
    id: int | None = None
    earliest_date: date | None = None
    latest_date: date | None = None
    remaining_duration: int | None = None
    status: TaskStatus = TaskStatus.PENDING

    def __post_init__(self) -> None:
        if self.remaining_duration is None:
            self.remaining_duration = self.duration


@dataclass
class AvailabilityBlock:
    block_date: date
    start_time: time
    end_time: time
    block_type: AvailabilityType
    id: int | None = None
    student_id: int = 1

    def __post_init__(self) -> None:
        if self.start_time >= self.end_time:
            raise ValueError("availability block must end after it starts")


@dataclass
class StudySession:
    task_id: int
    session_date: date
    start_time: time
    end_time: time
    planned_minutes: int
    id: int | None = None
    occurrence_id: int | None = None
    actual_minutes: int | None = None
    status: SessionStatus = SessionStatus.PLANNED
    slot_kind: SlotKind = SlotKind.PRIMARY
    cost: float = 0.0
    explanation: str = ""
    objective_score: float | None = None
    subjective_rating: int | None = None
    created_at: datetime = field(default_factory=_now)
    completed_at: datetime | None = None


@dataclass
class SchoolTimetableEntry:
    weekday: int
    period_no: int
    start_time: time
    end_time: time
    subject_id: int
    id: int | None = None
    student_id: int = 1


@dataclass(frozen=True)
class SchoolLesson:
    lesson_date: date
    period_no: int
    subject_lesson_no: int
    start_time: time
    end_time: time
    subject_id: int
    subject_name: str
    recorded_topic: str | None = None


@dataclass(frozen=True)
class RecallResult:
    objective_score: float     # 0..1 share of correctly recalled content
    subjective_rating: int     # 1..10 self-assessment


# ---- generic row <-> dataclass codec ------------------------------------- #

NON_COLUMN_FIELDS = {"topic_ids"}


def _unwrap_optional(hint: Any) -> Any:
    if typing.get_origin(hint) in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        return args[0]
    return hint


def _encode(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):          # must precede date (subclass)
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, RecurringRule):
        return json.dumps(value.to_dict())
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return value


def _decode(value: Any, hint: Any) -> Any:
    if value is None:
        return None
    hint = _unwrap_optional(hint)
    if hint is datetime:
        return datetime.fromisoformat(value)
    if hint is date:
        return date.fromisoformat(value)
    if hint is time:
        return time.fromisoformat(value)
    if hint is bool:
        return bool(value)
    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint(value)
    if hint is RecurringRule:
        return RecurringRule.from_dict(json.loads(value))
    if typing.get_origin(hint) is list:
        return json.loads(value)
    return value


def column_names(cls: type) -> list[str]:
    return [f.name for f in fields(cls) if f.name not in NON_COLUMN_FIELDS]


def model_to_row(obj: Any) -> dict[str, Any]:
    row = {n: _encode(getattr(obj, n)) for n in column_names(type(obj))}
    if row.get("id") is None:
        row.pop("id", None)
    return row


def row_to_model(cls: type, row: Mapping[str, Any], **extra: Any) -> Any:
    hints = typing.get_type_hints(cls)
    kwargs = {n: _decode(row[n], hints[n]) for n in column_names(cls) if n in row}
    kwargs.update(extra)
    return cls(**kwargs)


# =========================================================================== #
# B. MEMORY ENGINE  ("when should this topic be reviewed?")
# =========================================================================== #

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class MemoryEngine:
    """Stateless; independent from the scheduler and from calendars."""

    def __init__(self, config: MemoryConfig = MemoryConfig()) -> None:
        self.cfg = config

    # -- scores --------------------------------------------------------------
    def subjective_score(self, rating: int) -> float:
        c = self.cfg
        if not c.rating_min <= rating <= c.rating_max:
            raise ValueError(f"rating must be in {c.rating_min}..{c.rating_max}")
        return (rating - c.rating_min) / (c.rating_max - c.rating_min)

    def combined_score(self, objective_score: float, subjective_rating: int) -> float:
        if not 0.0 <= objective_score <= 1.0:
            raise ValueError("objective_score must be in [0, 1]")
        c = self.cfg
        total = c.objective_weight + c.subjective_weight
        return (c.objective_weight * objective_score
                + c.subjective_weight * self.subjective_score(subjective_rating)) / total

    # -- stability / difficulty ---------------------------------------------
    def performance_multiplier(self, q: float) -> float:
        for upper, mult in self.cfg.multiplier_bands:
            if q < upper:
                return mult
        return self.cfg.top_multiplier

    def difficulty_factor(self, difficulty: float) -> float:
        return self.cfg.difficulty_factor_base - self.cfg.difficulty_factor_slope * difficulty

    def update_difficulty(self, difficulty: float, q: float) -> float:
        c = self.cfg
        return _clamp(difficulty + c.difficulty_step * (c.difficulty_neutral_q - q), 0.0, 1.0)

    def update_stability(self, stability: float, q: float, difficulty: float) -> float:
        c = self.cfg
        s = stability * self.performance_multiplier(q) * self.difficulty_factor(difficulty)
        return _clamp(s, c.stability_min_days, c.stability_max_days)

    # -- forgetting curve ----------------------------------------------------
    @staticmethod
    def retrievability(stability_days: float, elapsed_days: float) -> float:
        return 2.0 ** (-elapsed_days / stability_days)

    def ideal_interval_days(self, stability_days: float) -> float:
        """t such that R(t) = target_recall  ->  t = -S * log2(target)."""
        return -stability_days * math.log2(self.cfg.target_recall)

    def interval_days(self, stability_days: float, relearning: bool = False) -> int:
        if relearning:
            return max(self.cfg.min_interval_days, self.cfg.relearning_interval_days)
        rounded = int(math.floor(self.ideal_interval_days(stability_days) + 0.5))
        return max(self.cfg.min_interval_days, rounded)

    def review_window(self, ideal: date, last_review: date) -> tuple[date, date]:
        earliest = ideal - timedelta(days=self.cfg.window_days_before)
        earliest = max(earliest, last_review + timedelta(days=self.cfg.min_interval_days))
        latest = max(ideal + timedelta(days=self.cfg.window_days_after), earliest)
        return earliest, latest

    # -- state transitions ---------------------------------------------------
    def initial_state(self, topic_id: int, event_date: date) -> MemoryState:
        c = self.cfg
        s = c.initial_stability_days
        return MemoryState(
            topic_id=topic_id, stability_days=s, difficulty=c.initial_difficulty,
            phase=MemoryPhase.NEW, last_review_date=event_date,
            next_review_date=event_date + timedelta(days=self.interval_days(s)))

    def on_learning_event(self, state: MemoryState | None, topic_id: int,
                          event_date: date) -> MemoryState:
        """New topic -> initial state.  Re-exposure restarts the clock, keeps stability."""
        if state is None:
            return self.initial_state(topic_id, event_date)
        last = max(state.last_review_date, event_date)
        nxt = last + timedelta(days=self.interval_days(
            state.stability_days, state.phase is MemoryPhase.RELEARNING))
        return replace(state, last_review_date=last, next_review_date=nxt, updated_at=_now())

    def apply_review(self, state: MemoryState, result: RecallResult,
                     review_date: date) -> MemoryState:
        q = self.combined_score(result.objective_score, result.subjective_rating)
        failed = q < self.cfg.failure_threshold_q
        new_d = self.update_difficulty(state.difficulty, q)
        d_for_s = new_d if self.cfg.use_updated_difficulty_for_stability else state.difficulty
        new_s = self.update_stability(state.stability_days, q, d_for_s)
        phase = MemoryPhase.RELEARNING if failed else MemoryPhase.REVIEW
        nxt = review_date + timedelta(days=self.interval_days(new_s, relearning=failed))
        return replace(
            state, stability_days=new_s, difficulty=new_d, phase=phase,
            last_review_date=review_date, next_review_date=nxt,
            review_count=state.review_count + 1,
            lapse_count=state.lapse_count + (1 if failed else 0),
            last_objective_score=result.objective_score,
            last_subjective_score=self.subjective_score(result.subjective_rating),
            last_combined_score=q, updated_at=_now())

    def review_urgency(self, state: MemoryState) -> float:
        """0..10 urgency handed to the scheduler (memory-side information only)."""
        c = self.cfg
        u = c.urgency_base + c.urgency_difficulty_gain * state.difficulty
        if state.phase is MemoryPhase.RELEARNING:
            u += c.urgency_relearning_bonus
        return _clamp(u, 0.0, 10.0)


# =========================================================================== #
# C. TASK ENGINE
# =========================================================================== #

class TaskEngine:
    def __init__(self, config: EngineConfig = DEFAULT_CONFIG) -> None:
        self.cfg = config
        self.memory = MemoryEngine(config.memory)

    # -- review tasks --------------------------------------------------------
    def review_from_memory(self, state: MemoryState, topic: Topic,
                           tags: Sequence[str] = ()) -> Task:
        m = self.cfg.memory
        earliest, latest = self.memory.review_window(state.next_review_date, state.last_review_date)
        dur = m.review_minutes_first_topic
        task = Task(
            title=f"Tekrar: {topic.name}", task_class=TaskClass.REVIEW, duration=dur,
            priority=m.review_priority, ideal_date=state.next_review_date,
            earliest_date=earliest, latest_date=latest, splittable=False, minimum_session=dur,
            tags=["#Review", *tags], review_source=ReviewSource.AUTOMATIC,
            urgency=self.memory.review_urgency(state), topic_ids=[topic.id] if topic.id else [])
        task.validate(self.cfg.task)
        return task

    def manual_review(self, title: str, topic_ids: Sequence[int], ideal_date: date,
                      duration: int | None = None, priority: int | None = None,
                      tags: Sequence[str] = ()) -> Task:
        m = self.cfg.memory
        topics = list(dict.fromkeys(topic_ids))               # de-duplicate, keep order
        if not topics:
            raise ValueError("a manual review needs at least one topic")
        dur = duration if duration is not None else (
            m.review_minutes_first_topic + m.review_minutes_extra_topic * (len(topics) - 1))
        task = Task(
            title=title, task_class=TaskClass.REVIEW, duration=dur,
            priority=priority if priority is not None else m.review_priority,
            ideal_date=ideal_date,
            earliest_date=ideal_date - timedelta(days=m.window_days_before),
            latest_date=ideal_date + timedelta(days=m.window_days_after),
            splittable=False, minimum_session=dur, tags=["#Review", *tags],
            review_source=ReviewSource.MANUAL, urgency=m.urgency_base,
            topic_ids=topics)
        task.validate(self.cfg.task)
        return task

    # -- deadline / recurring ------------------------------------------------
    def _resolve_min_session(self, duration: int, splittable: bool, minimum_session: int | None) -> int:
        if not splittable:
            return duration
        m = minimum_session if minimum_session else self.cfg.task.default_minimum_session
        return max(1, min(m, duration))

    def deadline_task(self, title: str, duration: int, deadline: date, priority: int = 5,
                      splittable: bool = True, minimum_session: int | None = None,
                      tags: Sequence[str] = (), topic_ids: Sequence[int] = (),
                      delay_cost: float = 0.0, exam_id: int | None = None) -> Task:
        task = Task(
            title=title, task_class=TaskClass.DEADLINE_TASK, duration=duration,
            priority=priority, deadline=deadline, splittable=splittable,
            minimum_session=self._resolve_min_session(max(duration, 1), splittable, minimum_session),
            tags=list(tags), topic_ids=list(topic_ids), delay_cost=delay_cost, exam_id=exam_id)
        task.validate(self.cfg.task)
        return task

    def recurring_task(self, title: str, duration: int, rule: RecurringRule, priority: int = 5,
                       tags: Sequence[str] = (), topic_ids: Sequence[int] = ()) -> Task:
        task = Task(
            title=title, task_class=TaskClass.RECURRING_TASK, duration=duration, priority=priority,
            recurring_rule=rule, splittable=False, minimum_session=duration,
            tags=list(tags), topic_ids=list(topic_ids))
        task.validate(self.cfg.task)
        return task

    def generate_occurrences(self, task: Task, task_id: int, start: date, end: date) -> list[TaskOccurrence]:
        """Occurrences with nominal date in [start, end] (recurrence rule is respected)."""
        rule = task.recurring_rule
        if rule is None or end < start:
            return []
        lo = max(start, rule.start_date) if rule.start_date else start
        hi = min(end, rule.end_date) if rule.end_date else end

        def make(nominal: date, earliest: date, latest: date) -> TaskOccurrence:
            return TaskOccurrence(task_id=task_id, occurrence_date=nominal, duration=task.duration,
                                  earliest_date=earliest, latest_date=latest)

        out: list[TaskOccurrence] = []
        if rule.kind in (RecurrenceKind.DAILY, RecurrenceKind.WEEKDAYS):
            d = lo
            while d <= hi:
                if rule.kind is RecurrenceKind.DAILY or d.weekday() in rule.weekdays:
                    out.append(make(d, d, d))
                d += timedelta(days=1)
            return out
        # TIMES_PER_WEEK: N nominal days spread over each Monday-Sunday week, window = whole week
        n = rule.times_per_week
        week = lo - timedelta(days=lo.weekday())
        while week <= hi:
            w_start = max(week, rule.start_date) if rule.start_date else week
            w_end = week + timedelta(days=6)
            if rule.end_date:
                w_end = min(w_end, rule.end_date)
            for k in range(n):
                nominal = week + timedelta(days=(k * 7) // n)
                if lo <= nominal <= hi and w_start <= nominal <= w_end:
                    out.append(make(nominal, w_start, w_end))
            week += timedelta(days=7)
        return out

    @staticmethod
    def split_duration(total: int, minimum: int, maximum: int) -> list[int]:
        """Evenly split ``total`` minutes into chunks within [minimum, maximum].

        If total < minimum the whole task stays one chunk. Deterministic.
        """
        if total <= 0:
            raise ValueError("total must be > 0")
        if minimum <= 0 or maximum < minimum:
            raise ValueError("require 0 < minimum <= maximum")
        if total <= maximum:
            return [total]
        count = math.ceil(total / maximum)
        while count > 1 and total // count < minimum:
            count -= 1
        base, extra = divmod(total, count)
        return [base + (1 if i < extra else 0) for i in range(count)]


# =========================================================================== #
# D. SCHEDULER  ("when in the student's real life should it happen?")
# =========================================================================== #

@dataclass(frozen=True)
class BusyInterval:
    day: date
    start_min: int
    end_min: int


@dataclass
class SchedulerInput:
    today: date
    now_minute: int                      # minutes since midnight; earlier time today is unusable
    tasks: list[Task]
    occurrences: list[TaskOccurrence] = field(default_factory=list)
    availability: list[AvailabilityBlock] = field(default_factory=list)
    busy: list[BusyInterval] = field(default_factory=list)   # completed sessions etc.
    exams: list[Exam] = field(default_factory=list)


@dataclass
class PlannedSession:
    task_id: int
    occurrence_id: int | None
    title: str
    task_class: TaskClass
    day: date
    start_min: int
    end_min: int
    kind: SlotKind
    cost: float
    explanation: str

    @property
    def minutes(self) -> int:
        return self.end_min - self.start_min

    def to_study_session(self) -> StudySession:
        return StudySession(
            task_id=self.task_id, occurrence_id=self.occurrence_id, session_date=self.day,
            start_time=_min_to_time(self.start_min), end_time=_min_to_time(self.end_min),
            planned_minutes=self.minutes, slot_kind=self.kind, cost=round(self.cost, 4),
            explanation=self.explanation)


@dataclass
class UnscheduledItem:
    task_id: int
    occurrence_id: int | None
    title: str
    reason: UnscheduledReason
    minutes: int
    detail: str = ""


@dataclass
class DayStats:
    day: date
    primary_capacity: int = 0      # PRIMARY minutes of the day (before buffer carve-out)
    buffer_minutes: int = 0
    planned_primary: int = 0
    planned_buffer: int = 0
    planned_reserve: int = 0

    @property
    def buffer_left(self) -> int:
        return self.buffer_minutes - self.planned_buffer


@dataclass
class SchedulePlan:
    sessions: list[PlannedSession] = field(default_factory=list)
    unscheduled: list[UnscheduledItem] = field(default_factory=list)
    day_stats: dict[date, DayStats] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def sessions_for(self, task_id: int) -> list[PlannedSession]:
        return [s for s in self.sessions if s.task_id == task_id]

    def total_cost(self) -> float:
        return sum(s.cost * s.minutes for s in self.sessions)


def _min_to_time(m: int) -> time:
    m = max(0, min(m, MINUTES_PER_DAY - 1))
    return time(m // 60, m % 60)


def _time_to_min(t: time) -> int:
    return t.hour * 60 + t.minute


def _merge(intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in sorted(i for i in intervals if i[1] > i[0]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _subtract(intervals: Sequence[tuple[int, int]], cuts: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for s, e in intervals:
        cur = s
        for cs, ce in cuts:
            if ce <= cur or cs >= e:
                continue
            if cs > cur:
                result.append((cur, cs))
            cur = max(cur, ce)
            if cur >= e:
                break
        if cur < e:
            result.append((cur, e))
    return result


@dataclass
class _Segment:
    day: date
    start: int
    end: int
    kind: SlotKind

    @property
    def free(self) -> int:
        return self.end - self.start


@dataclass
class _Item:
    task: Task
    occurrence: TaskOccurrence | None
    remaining: int
    min_session: int
    start: date                      # hard candidate window
    end: date
    ideal: date | None = None        # reviews: effective ideal date
    earliest: date | None = None
    latest: date | None = None
    deadline: date | None = None
    overdue: bool = False
    exam_date: date | None = None
    pressure: float = 0.0
    score: float = 0.0
    can_buffer: bool = False
    can_reserve: bool = False

    @property
    def klass(self) -> TaskClass:
        return self.task.task_class

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.task.id or 0, self.occurrence.id if self.occurrence and self.occurrence.id else 0)

    @property
    def label(self) -> str:
        return self.task.title


@dataclass
class _Cand:
    rate: float
    seg: _Segment
    length: int
    kind_cost: float
    time_cost: float
    load_cost: float
    split_cost: float

    @property
    def day(self) -> date:
        return self.seg.day


class Scheduler:
    def __init__(self, config: SchedulerConfig = SchedulerConfig()) -> None:
        self.cfg = config

    # ------------------------------------------------------------------ main
    def schedule(self, inp: SchedulerInput) -> SchedulePlan:
        cfg = self.cfg
        horizon_end = inp.today + timedelta(days=cfg.horizon_days - 1)
        plan = SchedulePlan()
        segs, stats = self._build_segments(inp, horizon_end)
        plan.day_stats = stats
        items = self._build_items(inp, segs, horizon_end, plan)
        items.sort(key=lambda i: (-round(i.score, 9), (i.end - i.start).days, i.sort_key))

        planned_load: dict[date, int] = {d: 0 for d in stats}
        review_load: dict[date, int] = {d: 0 for d in stats}
        review_cap = {d: int((s.primary_capacity - s.buffer_minutes) * cfg.review_day_cap_fraction)
                      for d, s in stats.items()}

        for item in items:
            eligible_before = self._eligible_free(item, segs)
            remaining = item.remaining
            while remaining > 0:
                cands = self._candidates(item, remaining, segs, stats, planned_load, review_load, review_cap)
                if not cands:
                    break
                best = min(cands, key=lambda c: (round(c.rate, 9), c.day, c.seg.start))
                seg = best.seg
                start, end = seg.start, seg.start + best.length
                seg.start = end
                remaining -= best.length
                planned_load[seg.day] += best.length
                if item.klass is TaskClass.REVIEW:
                    review_load[seg.day] += best.length
                st = stats[seg.day]
                if seg.kind is SlotKind.PRIMARY:
                    st.planned_primary += best.length
                elif seg.kind is SlotKind.BUFFER:
                    st.planned_buffer += best.length
                else:
                    st.planned_reserve += best.length
                plan.sessions.append(PlannedSession(
                    task_id=item.task.id or 0, occurrence_id=item.occurrence.id if item.occurrence else None,
                    title=item.label, task_class=item.klass, day=seg.day, start_min=start, end_min=end,
                    kind=seg.kind, cost=best.rate,
                    explanation=self._explain(item, best, cands, remaining)))
            if remaining > 0:
                self._report_shortfall(item, remaining, eligible_before, segs, horizon_end, plan)

        plan.sessions.sort(key=lambda s: (s.day, s.start_min, s.task_id))
        return plan

    # -------------------------------------------------------------- segments
    def _build_segments(self, inp: SchedulerInput, horizon_end: date
                        ) -> tuple[dict[date, list[_Segment]], dict[date, DayStats]]:
        by_day: dict[date, list[AvailabilityBlock]] = {}
        for b in inp.availability:
            by_day.setdefault(b.block_date, []).append(b)
        busy_by_day: dict[date, list[tuple[int, int]]] = {}
        for bi in inp.busy:
            busy_by_day.setdefault(bi.day, []).append((bi.start_min, bi.end_min))

        segs: dict[date, list[_Segment]] = {}
        stats: dict[date, DayStats] = {}
        day = inp.today
        while day <= horizon_end:
            blocks = by_day.get(day, [])

            def ivs(t: AvailabilityType) -> list[tuple[int, int]]:
                return _merge([(_time_to_min(b.start_time), _time_to_min(b.end_time))
                               for b in blocks if b.block_type is t])

            unavailable = ivs(AvailabilityType.UNAVAILABLE)
            primary_all = _subtract(ivs(AvailabilityType.PRIMARY), unavailable)
            reserve_all = _subtract(_subtract(ivs(AvailabilityType.RESERVE), unavailable), primary_all)
            runtime_cuts = list(unavailable) + busy_by_day.get(day, [])
            if day == inp.today:
                runtime_cuts.append((0, inp.now_minute))
            runtime_cuts = _merge(runtime_cuts)
            primary = _subtract(primary_all, runtime_cuts)
            reserve = _subtract(reserve_all, runtime_cuts)

            capacity = sum(e - s for s, e in primary_all)
            buffer_target = int(capacity * self.cfg.buffer_fraction)
            segments: list[_Segment] = []
            buffer_left = buffer_target
            buffer_segments: list[_Segment] = []
            for s, e in reversed(primary):            # carve buffer from the END of the day
                take = min(buffer_left, e - s)
                if take > 0:
                    buffer_segments.append(_Segment(day, e - take, e, SlotKind.BUFFER))
                    buffer_left -= take
                if e - take > s:
                    segments.append(_Segment(day, s, e - take, SlotKind.PRIMARY))
            segments.extend(buffer_segments)
            segments.extend(_Segment(day, s, e, SlotKind.RESERVE) for s, e in reserve)
            segments.sort(key=lambda g: (g.start, g.kind.value))
            segs[day] = segments
            stats[day] = DayStats(day=day, primary_capacity=capacity,
                                  buffer_minutes=buffer_target - buffer_left)
            day += timedelta(days=1)
        return segs, stats

    # ----------------------------------------------------------------- items
    def _build_items(self, inp: SchedulerInput, segs: dict[date, list[_Segment]],
                     horizon_end: date, plan: SchedulePlan) -> list[_Item]:
        cfg = self.cfg
        today = inp.today
        exam_dates = self._exam_lookup(inp)
        items: list[_Item] = []
        occ_by_task: dict[int, list[TaskOccurrence]] = {}
        for o in inp.occurrences:
            if o.status is TaskStatus.PENDING and (o.remaining_duration or 0) > 0:
                occ_by_task.setdefault(o.task_id, []).append(o)

        def expired(task: Task, occ: TaskOccurrence | None, minutes: int, why: str) -> None:
            plan.unscheduled.append(UnscheduledItem(
                task.id or 0, occ.id if occ else None, task.title,
                UnscheduledReason.WINDOW_EXPIRED, minutes, why))

        for task in sorted(inp.tasks, key=lambda t: t.id or 0):
            if task.status is not TaskStatus.PENDING:
                continue
            exam_date = self._task_exam_date(task, exam_dates, inp.exams, today)

            if task.task_class is TaskClass.RECURRING_TASK:
                for occ in sorted(occ_by_task.get(task.id or 0, []), key=lambda o: o.occurrence_date):
                    earliest = occ.earliest_date or occ.occurrence_date
                    latest = occ.latest_date or occ.occurrence_date
                    if latest < today:
                        expired(task, occ, occ.remaining_duration or 0, "tekrar penceresi geçti")
                        continue
                    start, end = max(today, earliest), min(latest, horizon_end)
                    if start > end:
                        continue                          # beyond horizon: not due yet
                    items.append(self._finish_item(_Item(
                        task=task, occurrence=occ, remaining=occ.remaining_duration or 0,
                        min_session=occ.remaining_duration or 0, start=start, end=end,
                        ideal=occ.occurrence_date, earliest=earliest, latest=latest,
                        exam_date=exam_date), segs, today))
                continue

            remaining = task.remaining_duration or 0
            if remaining <= 0:
                continue
            min_session = remaining
            if task.splittable:
                min_session = max(1, min(task.minimum_session or remaining, remaining))

            if task.task_class is TaskClass.REVIEW:
                ideal = task.ideal_date or today
                earliest = task.earliest_date or ideal
                latest = task.latest_date or ideal
                if cfg.exam_pull_forward and exam_date is not None:
                    pulled = exam_date - timedelta(days=cfg.exam_pull_forward_days)
                    if pulled < ideal:
                        ideal = pulled
                        earliest = min(earliest, ideal)
                        latest = max(ideal, min(latest, exam_date))
                start = max(today, earliest - timedelta(days=cfg.review_max_early_days))
                if start > horizon_end:
                    continue                              # not due within the horizon
                items.append(self._finish_item(_Item(
                    task=task, occurrence=None, remaining=remaining, min_session=min_session,
                    start=start, end=horizon_end, ideal=ideal, earliest=earliest, latest=latest,
                    exam_date=exam_date), segs, today))
            else:  # DEADLINE_TASK
                deadline = task.deadline or horizon_end
                overdue = deadline < today
                start = max(today, task.earliest_date or today)
                end = horizon_end if overdue else min(deadline, horizon_end)
                if start > end:
                    expired(task, None, remaining, "başlangıç tarihi son tarihten sonra")
                    continue
                items.append(self._finish_item(_Item(
                    task=task, occurrence=None, remaining=remaining, min_session=min_session,
                    start=start, end=end, deadline=deadline, overdue=overdue,
                    exam_date=exam_date), segs, today))
        return items

    def _finish_item(self, it: _Item, segs: dict[date, list[_Segment]], today: date) -> _Item:
        """Compute pressure, ordering score and slot-kind eligibility."""
        cfg = self.cfg
        task = it.task
        score = cfg.w_priority * task.priority / 10.0 + cfg.w_delay_cost * task.delay_cost / 10.0
        if it.klass is TaskClass.DEADLINE_TASK:
            if it.overdue:
                it.pressure = cfg.overdue_pressure
            else:
                cap = sum(s.free for d in _days(it.start, it.end) for s in segs.get(d, [])
                          if s.kind is not SlotKind.RESERVE)
                days_left = max(0, ((it.deadline or today) - today).days)
                it.pressure = 0.5 / (1 + days_left) + 0.5 * min(1.0, it.remaining / max(cap, 1))
            score += cfg.w_deadline * it.pressure
            it.can_buffer = it.overdue or it.pressure >= cfg.buffer_pressure_threshold
        elif it.klass is TaskClass.REVIEW:
            late_days = max(0, (today - (it.ideal or today)).days)
            comp = _clamp(task.urgency / 10.0, 0.0, 1.0) + min(
                cfg.review_lateness_cap, cfg.review_lateness_gain * late_days)
            score += cfg.w_review * comp
        else:
            score += cfg.w_routine
        if it.exam_date is not None:
            d = (it.exam_date - today).days
            if 0 <= d <= cfg.exam_horizon_days:
                score += cfg.w_exam * (1.0 - d / cfg.exam_horizon_days)
        it.score = score
        it.can_reserve = it.klass in cfg.reserve_eligible_classes
        return it

    @staticmethod
    def _exam_lookup(inp: SchedulerInput) -> dict[int, date]:
        """topic_id -> nearest upcoming exam date."""
        result: dict[int, date] = {}
        for ex in sorted(inp.exams, key=lambda e: e.exam_date):
            if ex.exam_date < inp.today:
                continue
            for tid in ex.topic_ids:
                result.setdefault(tid, ex.exam_date)
        return result

    @staticmethod
    def _task_exam_date(task: Task, by_topic: dict[int, date], exams: list[Exam], today: date) -> date | None:
        dates = [by_topic[t] for t in task.topic_ids if t in by_topic]
        if task.exam_id is not None:
            dates += [e.exam_date for e in exams if e.id == task.exam_id and e.exam_date >= today]
        return min(dates) if dates else None

    # ------------------------------------------------------------ candidates
    def _eligible(self, item: _Item, seg: _Segment) -> bool:
        if seg.free <= 0:
            return False
        if seg.kind is SlotKind.BUFFER:
            return item.can_buffer
        if seg.kind is SlotKind.RESERVE:
            return item.can_reserve
        return True

    def _eligible_free(self, item: _Item, segs: dict[date, list[_Segment]]) -> int:
        return sum(s.free for d in _days(item.start, item.end) for s in segs.get(d, [])
                   if self._eligible(item, s))

    def _chunk_length(self, item: _Item, remaining: int, free: int) -> int:
        if not item.task.splittable:
            return remaining if free >= remaining else 0
        cap = min(free, self.cfg.max_session_minutes)
        length = min(remaining, cap)
        if length == remaining:
            return length
        m = item.min_session
        if length < m:
            return 0
        if remaining - length < m:                      # avoid orphaning a tiny remainder
            shorter = remaining - m
            if shorter >= m:
                return shorter
            return remaining if remaining <= cap else 0
        return length

    def _kind_cost(self, kind: SlotKind) -> float:
        return {SlotKind.PRIMARY: self.cfg.slot_cost_primary, SlotKind.BUFFER: self.cfg.slot_cost_buffer,
                SlotKind.RESERVE: self.cfg.slot_cost_reserve}[kind]

    def _time_cost(self, item: _Item, day: date, today_hint: date | None = None) -> float:
        cfg = self.cfg
        if item.klass is TaskClass.REVIEW:
            ideal, earliest, latest = item.ideal, item.earliest, item.latest
            assert ideal is not None and earliest is not None and latest is not None
            delta = (day - ideal).days
            base = cfg.review_early_cost_per_day * -delta if delta < 0 else cfg.review_late_cost_per_day * delta
            outside = (earliest - day).days if day < earliest else (day - latest).days if day > latest else 0
            if outside > 0:
                base += cfg.review_outside_window_penalty + cfg.review_outside_window_per_day * outside
            return base * (cfg.review_urgency_base + item.task.urgency / 10.0)
        if item.klass is TaskClass.DEADLINE_TASK:
            anchor = item.start
            if item.overdue:
                return cfg.overdue_asap_cost_per_day * (day - anchor).days
            span = max(1, ((item.deadline or day) - anchor).days)
            p = (day - anchor).days / span
            return cfg.deadline_risk_weight * p * (0.5 + item.task.priority / 10.0)
        nominal = item.ideal or day
        return cfg.recurring_distance_cost_per_day * abs((day - nominal).days)

    def _candidates(self, item: _Item, remaining: int, segs: dict[date, list[_Segment]],
                    stats: dict[date, DayStats], load: dict[date, int],
                    review_load: dict[date, int], review_cap: dict[date, int]) -> list[_Cand]:
        cfg = self.cfg
        out: list[_Cand] = []
        for day in _days(item.start, item.end):
            cap_left = review_cap.get(day, 0) - review_load.get(day, 0)
            capacity = max(1, stats[day].primary_capacity)
            time_cost = self._time_cost(item, day)
            load_cost = cfg.load_balance_weight * load.get(day, 0) / capacity
            for seg in segs.get(day, []):
                if not self._eligible(item, seg):
                    continue
                if item.klass is TaskClass.REVIEW and seg.kind is SlotKind.RESERVE:
                    continue
                free = min(seg.free, cap_left) if item.klass is TaskClass.REVIEW else seg.free
                length = self._chunk_length(item, remaining, free)
                if length <= 0:
                    continue
                kind_cost = self._kind_cost(seg.kind)
                split_cost = cfg.split_penalty if length < remaining else 0.0
                out.append(_Cand(kind_cost + time_cost + load_cost + split_cost, seg, length,
                                 kind_cost, time_cost, load_cost, split_cost))
        return out

    # ---------------------------------------------------------- explanations
    def _explain(self, item: _Item, best: _Cand, cands: list[_Cand], remaining_after: int) -> str:
        day, seg = best.day, best.seg
        parts = [f"{item.klass.value}: {item.label}",
                 f"{day:%d.%m} {_min_to_time(seg.start - best.length).strftime('%H:%M')} "
                 f"({best.length} dk, {seg.kind.value})",
                 f"sıralama skoru={item.score:.2f}"]
        if item.klass is TaskClass.REVIEW and item.ideal:
            dev = (day - item.ideal).days
            inside = item.earliest is not None and item.latest is not None and item.earliest <= day <= item.latest
            parts.append(f"ideal tarih {item.ideal:%d.%m}, sapma {dev:+d} gün, "
                         f"{'pencere içinde' if inside else 'pencere DIŞINDA'}")
            if dev != 0:
                on_ideal = [c for c in cands if c.day == item.ideal]
                parts.append("ideal günde uygun boşluk yok" if not on_ideal
                             else "ideal gün daha maliyetli (yük/aciliyet dengesi)")
        elif item.klass is TaskClass.DEADLINE_TASK and item.deadline:
            if item.overdue:
                parts.append(f"GECİKMİŞ (son tarih {item.deadline:%d.%m}); en erken uygun yere konuldu")
            else:
                parts.append(f"son tarih {item.deadline:%d.%m}, {(item.deadline - day).days} gün önce; "
                             f"baskı={item.pressure:.2f}")
        elif item.klass is TaskClass.RECURRING_TASK and item.ideal:
            parts.append(f"rutin görev; nominal gün {item.ideal:%d.%m}")
        if seg.kind is SlotKind.RESERVE:
            has_primary = any(c.seg.kind is SlotKind.PRIMARY for c in cands)
            parts.append("RESERVE kullanıldı: " + ("PRIMARY seçenekleri daha maliyetli"
                                                    if has_primary else "pencerede uygun PRIMARY boşluk yok"))
        elif seg.kind is SlotKind.BUFFER:
            parts.append("BUFFER kullanıldı: görev acil, PRIMARY yetmedi")
        if best.length < remaining_after + best.length:
            parts.append(f"bölünmüş görev, kalan {remaining_after} dk")
        return "; ".join(parts)

    def _report_shortfall(self, item: _Item, remaining: int, eligible_before: int,
                          segs: dict[date, list[_Segment]], horizon_end: date, plan: SchedulePlan) -> None:
        eligible_now = self._eligible_free(item, segs)
        if eligible_before == 0:
            reason, detail = UnscheduledReason.NO_AVAILABILITY, "uygun çalışma zamanı yok"
        elif eligible_now < remaining:
            reason, detail = UnscheduledReason.INSUFFICIENT_CAPACITY, "pencere içinde yeterli kapasite yok"
        else:
            reason, detail = (UnscheduledReason.NO_CONTIGUOUS_SLOT,
                              "yeterince büyük ya da günlük review sınırına uygun boşluk yok")
        plan.unscheduled.append(UnscheduledItem(
            item.task.id or 0, item.occurrence.id if item.occurrence else None,
            item.label, reason, remaining, detail))
        if item.deadline is not None and item.deadline <= horizon_end:
            plan.warnings.append(
                f"Son tarih riski: '{item.label}' için {remaining} dk yerleştirilemedi ({detail}).")
        elif item.overdue:
            plan.warnings.append(f"Gecikmiş görev '{item.label}' tamamen yerleştirilemedi ({detail}).")


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


# =========================================================================== #
# E. APPLICATION SERVICE  (the only API ui.py uses; all persistence via Database)
# =========================================================================== #

SUBJECT_COLORS = ["#4F7CAC", "#C8553D", "#588157", "#9C6ADE", "#D9A441", "#2A9D8F", "#E07A9B", "#6C757D"]


@dataclass
class LearningEventView:
    event: LearningEvent
    topic_name: str
    unit_id: int | None = None
    unit_name: str | None = None


@dataclass
class MemoryView:
    topic_name: str
    state: MemoryState
    unit_id: int | None = None
    unit_name: str | None = None


@dataclass
class SessionView:
    session: StudySession
    title: str
    task_class: TaskClass

    def display_state(self, now: datetime) -> str:
        """completed / overdue / planned (overdue = start passed without completion)."""
        s = self.session
        if s.status is SessionStatus.COMPLETED:
            return "completed"
        if s.status in (SessionStatus.MISSED, SessionStatus.SKIPPED):
            return "overdue"
        start = datetime.combine(s.session_date, s.start_time)
        return "overdue" if start < now else "planned"


class PlannerService:
    def __init__(self, db: Database, config: EngineConfig = DEFAULT_CONFIG) -> None:
        self.db = db
        raw = db.get_setting("config_overrides")
        self.config = config.with_overrides(json.loads(raw)) if raw else config
        self._build_engines()
        self.student_id = self._ensure_student()
        self.last_plan: SchedulePlan | None = None

    def _build_engines(self) -> None:
        self.memory = MemoryEngine(self.config.memory)
        self.tasks = TaskEngine(self.config)
        self.scheduler = Scheduler(self.config.scheduler)

    def update_config(self, overrides: Mapping[str, Mapping[str, Any]]) -> None:
        """Persist scalar parameter overrides, e.g. {'scheduler': {'buffer_fraction': 0.3}}."""
        new = self.config.with_overrides(overrides)       # validates
        merged = json.loads(self.db.get_setting("config_overrides", "{}") or "{}")
        for section, values in overrides.items():
            merged.setdefault(section, {}).update(values)
        self.db.set_setting("config_overrides", json.dumps(merged))
        self.config = new
        self._build_engines()

    def _ensure_student(self) -> int:
        rows = self.db.select("students", order_by=["id"])
        if rows:
            return int(rows[0]["id"])
        return self.db.insert("students", model_to_row(Student(name="Öğrenci")))

    # ------------------------------------------------------------- subjects
    def list_subjects(self) -> list[Subject]:
        rows = self.db.select("subjects", {"student_id": self.student_id}, order_by=["name"])
        return [row_to_model(Subject, r) for r in rows]

    def add_subject(self, name: str) -> Subject:
        name = name.strip()
        if not name:
            raise ValueError("ders adı boş olamaz")
        color = SUBJECT_COLORS[len(self.db.select("subjects", {"student_id": self.student_id})) % len(SUBJECT_COLORS)]
        subj = Subject(name=name, student_id=self.student_id, color=color)
        subj.id = self.db.insert("subjects", model_to_row(subj))
        return subj

    def rename_subject(self, subject_id: int, name: str) -> None:
        if not name.strip():
            raise ValueError("ders adı boş olamaz")
        self.db.update("subjects", subject_id, {"name": name.strip()})

    def delete_subject(self, subject_id: int) -> None:
        with self.db.transaction():
            topic_ids = [t["id"] for t in self.db.select("topics", {"subject_id": subject_id})]
            self.db.delete_review_tasks_for_topics(topic_ids)
            self.db.delete("subjects", {"id": subject_id})

    # ---------------------------------------------------------------- units
    def list_units(self, subject_id: int) -> list[Unit]:
        rows = self.db.units_for_subject(subject_id)
        return [row_to_model(Unit, r) for r in rows]

    def add_unit(self, subject_id: int, name: str, order_no: int | None = None,
                 start_date: date | None = None, end_date: date | None = None) -> Unit:
        name = name.strip()
        if not name:
            raise ValueError("ünite adı boş olamaz")
        if order_no is None:
            existing = self.list_units(subject_id)
            order_no = (max((u.order_no for u in existing), default=0) + 1)
        unit = Unit(name=name, subject_id=subject_id, order_no=order_no,
                    start_date=start_date, end_date=end_date)
        unit.id = self.db.insert("units", model_to_row(unit))
        return unit

    def get_or_create_unit(self, subject_id: int, name: str) -> Unit:
        name = name.strip()
        if not name:
            raise ValueError("ünite adı boş olamaz")
        rows = self.db.select("units", {"subject_id": subject_id, "name": name})
        if rows:
            return row_to_model(Unit, rows[0])
        return self.add_unit(subject_id, name)

    def rename_unit(self, unit_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("ünite adı boş olamaz")
        self.db.update("units", unit_id, {"name": name})

    def update_unit(self, unit_id: int, **kwargs: Any) -> None:
        vals: dict[str, Any] = {}
        if "name" in kwargs and kwargs["name"] is not None:
            n = str(kwargs["name"]).strip()
            if not n:
                raise ValueError("ünite adı boş olamaz")
            vals["name"] = n
        for k in ("order_no", "start_date", "end_date"):
            if k in kwargs:
                vals[k] = _encode(kwargs[k])
        if vals:
            self.db.update("units", unit_id, vals)

    def delete_unit(self, unit_id: int) -> None:
        self.db.delete("units", {"id": unit_id})

    # --------------------------------------------------------------- topics
    def list_topics(self, subject_id: int, unit_id: int | None = None) -> list[Topic]:
        where: dict[str, Any] = {"subject_id": subject_id}
        if unit_id is not None:
            where["unit_id"] = unit_id
        return [row_to_model(Topic, r) for r in self.db.select("topics", where, ["name"])]

    def get_or_create_topic(self, subject_id: int, name: str, unit_id: int | None = None) -> Topic:
        name = name.strip()
        if not name:
            raise ValueError("konu adı boş olamaz")
        rows = self.db.select("topics", {"subject_id": subject_id, "name": name})
        if rows:
            t = row_to_model(Topic, rows[0])
            if unit_id is not None and t.unit_id != unit_id:
                self.db.update("topics", t.id, {"unit_id": unit_id})
                t.unit_id = unit_id
            return t
        topic = Topic(name=name, subject_id=subject_id, unit_id=unit_id)
        topic.id = self.db.insert("topics", model_to_row(topic))
        return topic

    def topic_labels(self, topic_ids: Sequence[int]) -> list[str]:
        out = []
        for tid in topic_ids:
            row = self.db.get("topics", tid)
            if row:
                subj = self.db.get("subjects", row["subject_id"])
                out.append(f"{subj['name'] if subj else '?'} / {row['name']}")
        return out

    # ------------------------------------------------------ learning events
    def list_learning_events(self, subject_id: int) -> list[LearningEventView]:
        return [LearningEventView(
                    row_to_model(LearningEvent, r),
                    r["topic_name"],
                    r.get("unit_id"),
                    r.get("unit_name"))
                for r in self.db.learning_events_for_subject(subject_id)]

    def add_learning_event(self, subject_id: int, event_date: date, topic_name: str,
                           period_start: int | None = None, period_end: int | None = None,
                           notes: str = "", unit_id: int | None = None) -> LearningEvent:
        """Subject -> Unit / Topic -> LearningEvent -> MemoryState -> automatic Review task."""
        if period_start is not None and period_end is not None and period_end < period_start:
            raise ValueError("ders saati bitişi başlangıçtan önce olamaz")
        with self.db.transaction():
            topic = self.get_or_create_topic(subject_id, topic_name, unit_id=unit_id)
            assert topic.id is not None
            ev = LearningEvent(topic_id=topic.id, event_date=event_date, period_start=period_start,
                               period_end=period_end, notes=notes.strip())
            ev.id = self.db.insert("learning_events", model_to_row(ev))
            row = self.db.get("memory_states", topic.id, key="topic_id")
            old = row_to_model(MemoryState, row) if row else None
            new = self.memory.on_learning_event(old, topic.id, event_date)
            self.db.upsert("memory_states", model_to_row(new), conflict="topic_id")
            self._sync_review_task(topic.id)
        return ev

    def delete_learning_event(self, event_id: int) -> None:
        self.db.delete("learning_events", {"id": event_id})

    def list_memory(self, subject_id: int) -> list[MemoryView]:
        return [MemoryView(
                    r["topic_name"],
                    row_to_model(MemoryState, r),
                    r.get("unit_id"),
                    r.get("unit_name"))
                for r in self.db.memory_states_for_subject(subject_id)]

    # ----------------------------------------------------------------- tasks
    def _task_from_row(self, row: Mapping[str, Any], links: Mapping[int, list[int]] | None = None) -> Task:
        links = links if links is not None else self.db.topic_link_map("task_topic_links")
        return row_to_model(Task, row, topic_ids=list(links.get(int(row["id"]), [])))

    def get_task(self, task_id: int) -> Task | None:
        row = self.db.get("tasks", task_id)
        return self._task_from_row(row) if row else None

    def _insert_task(self, task: Task) -> int:
        task.student_id = self.student_id
        task.validate(self.config.task)
        task.id = self.db.insert("tasks", model_to_row(task))
        self.db.set_topic_links("task_topic_links", task.id, task.topic_ids)
        return task.id

    def update_task(self, task: Task) -> None:
        if task.id is None:
            raise ValueError("task has no id")
        task.validate(self.config.task)
        task.updated_at = _now()
        row = model_to_row(task)
        row.pop("id", None)
        with self.db.transaction():
            self.db.update("tasks", task.id, row)
            self.db.set_topic_links("task_topic_links", task.id, task.topic_ids)

    def add_deadline_task(self, **kwargs: Any) -> Task:
        task = self.tasks.deadline_task(**kwargs)
        self._insert_task(task)
        return task

    def add_recurring_task(self, today: date | None = None, **kwargs: Any) -> Task:
        task = self.tasks.recurring_task(**kwargs)
        with self.db.transaction():
            self._insert_task(task)
            self._materialize_occurrences(today or date.today())
        return task

    def add_manual_review(self, **kwargs: Any) -> Task:
        task = self.tasks.manual_review(**kwargs)
        self._insert_task(task)
        return task

    def cancel_task(self, task_id: int) -> None:
        with self.db.transaction():
            self.db.update("tasks", task_id, {"status": TaskStatus.CANCELLED.value,
                                              "updated_at": _encode(_now())})
            self.db.delete("study_sessions", {"task_id": task_id, "status": "PLANNED"})

    def delete_task(self, task_id: int) -> None:
        self.db.delete("tasks", {"id": task_id})

    def list_tasks(self, view: str = "all", today: date | None = None) -> list[Task]:
        today = today or date.today()
        links = self.db.topic_link_map("task_topic_links")
        tasks = [self._task_from_row(r, links) for r in self.db.select("tasks", order_by=["id"])]
        P = TaskStatus.PENDING

        def sort_key(t: Task) -> tuple[date, int]:
            return (t.deadline or t.ideal_date or date.max, t.id or 0)

        if view == "review":
            tasks = [t for t in tasks if t.task_class is TaskClass.REVIEW and t.status is P]
        elif view == "deadline":
            tasks = [t for t in tasks if t.task_class is TaskClass.DEADLINE_TASK and t.status is P]
        elif view == "recurring":
            tasks = [t for t in tasks if t.task_class is TaskClass.RECURRING_TASK and t.status is P]
        elif view == "overdue":
            tasks = [t for t in tasks if t.is_overdue(today)]
        elif view == "completed":
            tasks = [t for t in tasks if t.status is TaskStatus.COMPLETED]
        else:
            tasks = [t for t in tasks if t.status is not TaskStatus.CANCELLED]
        return sorted(tasks, key=sort_key)

    # ---- review synchronisation (memory -> task pool) -----------------------
    def _sync_review_task(self, topic_id: int) -> None:
        row = self.db.get("memory_states", topic_id, key="topic_id")
        trow = self.db.get("topics", topic_id)
        if not row or not trow:
            return
        state = row_to_model(MemoryState, row)
        topic = row_to_model(Topic, trow)
        subj = self.db.get("subjects", topic.subject_id)
        new = self.tasks.review_from_memory(state, topic, tags=[f"#{subj['name']}"] if subj else [])
        existing = self.db.find_review_tasks(topic_id, ReviewSource.AUTOMATIC.value)
        if existing:
            self.db.update("tasks", existing[0]["id"], {
                "ideal_date": _encode(new.ideal_date), "earliest_date": _encode(new.earliest_date),
                "latest_date": _encode(new.latest_date), "urgency": new.urgency,
                "updated_at": _encode(_now())})
            for dup in existing[1:]:
                self.db.delete("tasks", {"id": dup["id"]})
        else:
            self._insert_task(new)

    def sync_all_review_tasks(self) -> None:
        for r in self.db.select("memory_states"):
            self._sync_review_task(int(r["topic_id"]))

    # ----------------------------------------------------------- occurrences
    def _materialize_occurrences(self, today: date) -> None:
        horizon = today + timedelta(days=self.config.task.occurrence_horizon_days)
        links = self.db.topic_link_map("task_topic_links")
        for row in self.db.select("tasks", {"task_class": "RECURRING_TASK", "status": "PENDING"}):
            task = self._task_from_row(row, links)
            assert task.id is not None
            have = {r["occurrence_date"] for r in self.db.select("task_occurrences", {"task_id": task.id})}
            for occ in self.tasks.generate_occurrences(task, task.id, today, horizon):
                if occ.occurrence_date.isoformat() not in have:
                    self.db.insert("task_occurrences", model_to_row(occ))
        for r in self.db.select("task_occurrences", {"status": "PENDING"}):
            latest = r["latest_date"] or r["occurrence_date"]
            if latest < today.isoformat():
                self.db.update("task_occurrences", r["id"], {"status": TaskStatus.MISSED.value})

    # ---------------------------------------------------------- availability
    def add_availability(self, day: date, start: time, end: time, kind: AvailabilityType) -> AvailabilityBlock:
        blk = AvailabilityBlock(block_date=day, start_time=start, end_time=end, block_type=kind,
                                student_id=self.student_id)
        blk.id = self.db.insert("availability_blocks", model_to_row(blk))
        return blk

    def add_availability_range(self, start_date: date, end_date: date, weekdays: Sequence[int],
                               start: time, end: time, kind: AvailabilityType) -> int:
        count = 0
        with self.db.transaction():
            for d in _days(start_date, end_date):
                if d.weekday() in weekdays:
                    self.add_availability(d, start, end, kind)
                    count += 1
        return count

    def list_availability(self, start: date, end: date) -> list[AvailabilityBlock]:
        rows = self.db.select_range("availability_blocks", "block_date", start.isoformat(), end.isoformat(),
                                    {"student_id": self.student_id}, ["block_date", "start_time"])
        return [row_to_model(AvailabilityBlock, r) for r in rows]

    def delete_availability(self, block_id: int) -> None:
        self.db.delete("availability_blocks", {"id": block_id})

    # ------------------------------------------------------ school timetable
    def list_timetable(self) -> list[SchoolTimetableEntry]:
        rows = self.db.select("school_timetable", {"student_id": self.student_id}, ["weekday", "period_no"])
        return [row_to_model(SchoolTimetableEntry, r) for r in rows]

    def list_school_lessons(self, start: date, end: date) -> list[SchoolLesson]:
        """Expand the fixed weekly timetable into dated lessons for a calendar range."""
        entries = self.list_timetable()
        subjects = {s.id: s.name for s in self.list_subjects()}
        subject_order: dict[tuple[int, int], int] = {}
        subject_counts: dict[int, int] = {}
        for entry in entries:
            subject_counts[entry.subject_id] = subject_counts.get(entry.subject_id, 0) + 1
            subject_order[(entry.weekday, entry.period_no)] = subject_counts[entry.subject_id]

        recorded: dict[tuple[int, date, int], str] = {}
        for subject in self.list_subjects():
            for event_view in self.list_learning_events(subject.id):
                event = event_view.event
                if event.period_start is not None:
                    recorded[(subject.id, event.event_date, event.period_start)] = event_view.topic_name

        by_weekday: dict[int, list[SchoolTimetableEntry]] = {}
        for entry in entries:
            by_weekday.setdefault(entry.weekday, []).append(entry)

        lessons: list[SchoolLesson] = []
        for day in _days(start, end):
            for entry in by_weekday.get(day.weekday(), []):
                ordinal = subject_order[(entry.weekday, entry.period_no)]
                lessons.append(SchoolLesson(
                    lesson_date=day,
                    period_no=entry.period_no,
                    subject_lesson_no=ordinal,
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                    subject_id=entry.subject_id,
                    subject_name=subjects[entry.subject_id],
                    recorded_topic=recorded.get((entry.subject_id, day, ordinal)),
                ))
        return lessons

    def set_timetable_entry(self, weekday: int, period_no: int, start: time, end: time, subject_id: int) -> None:
        entry = SchoolTimetableEntry(weekday=weekday, period_no=period_no, start_time=start,
                                     end_time=end, subject_id=subject_id, student_id=self.student_id)
        with self.db.transaction():
            self.db.delete("school_timetable", {"student_id": self.student_id, "weekday": weekday,
                                                "period_no": period_no})
            self.db.insert("school_timetable", model_to_row(entry))

    def delete_timetable_entry(self, entry_id: int) -> None:
        self.db.delete("school_timetable", {"id": entry_id})

    # ----------------------------------------------------------------- exams
    def list_exams(self) -> list[Exam]:
        links = self.db.topic_link_map("exam_topic_links")
        rows = self.db.select("exams", {"student_id": self.student_id}, ["exam_date", "id"])
        return [row_to_model(Exam, r, topic_ids=links.get(int(r["id"]), [])) for r in rows]

    def add_exam(self, title: str, exam_date: date, subject_id: int | None = None,
                 topic_ids: Sequence[int] = ()) -> Exam:
        if not title.strip():
            raise ValueError("sınav başlığı boş olamaz")
        ex = Exam(title=title.strip(), exam_date=exam_date, student_id=self.student_id,
                  subject_id=subject_id, topic_ids=list(topic_ids))
        with self.db.transaction():
            ex.id = self.db.insert("exams", model_to_row(ex))
            self.db.set_topic_links("exam_topic_links", ex.id, ex.topic_ids)
        return ex

    def delete_exam(self, exam_id: int) -> None:
        self.db.delete("exams", {"id": exam_id})

    # -------------------------------------------------------------- planning
    def _build_input(self, today: date, now_minute: int) -> SchedulerInput:
        horizon_end = today + timedelta(days=self.config.scheduler.horizon_days - 1)
        links = self.db.topic_link_map("task_topic_links")
        tasks = [self._task_from_row(r, links)
                 for r in self.db.select("tasks", {"status": "PENDING"}, ["id"])]
        occs = [row_to_model(TaskOccurrence, r) for r in self.db.select("task_occurrences", {"status": "PENDING"})]
        availability = self.list_availability(today, horizon_end)
        busy: list[BusyInterval] = []
        for r in self.db.select_range("study_sessions", "session_date", today.isoformat(),
                                      horizon_end.isoformat(), {"status": "COMPLETED"}):
            s = row_to_model(StudySession, r)
            start = _time_to_min(s.start_time)
            busy.append(BusyInterval(s.session_date, start, start + (s.actual_minutes or s.planned_minutes)))
        return SchedulerInput(today=today, now_minute=now_minute, tasks=tasks, occurrences=occs,
                              availability=availability, busy=busy, exams=self.list_exams())

    def replan(self, now: datetime | None = None) -> SchedulePlan:
        """(Re)build the plan from `now` on. Safe to call at any time (dynamic replanning)."""
        now = now or datetime.now()
        today = now.date()
        with self.db.transaction():
            self.db.mark_stale_sessions_missed(today.isoformat(), now.strftime("%H:%M"))
            self.db.delete_planned_sessions()
            self.sync_all_review_tasks()
            self._materialize_occurrences(today)
            plan = self.scheduler.schedule(self._build_input(today, now.hour * 60 + now.minute))
            for ps in plan.sessions:
                self.db.insert("study_sessions", model_to_row(ps.to_study_session()))
        self.last_plan = plan
        return plan

    def list_sessions(self, start: date, end: date) -> list[SessionView]:
        rows = self.db.select_range("study_sessions", "session_date", start.isoformat(), end.isoformat(),
                                    order_by=["session_date", "start_time"])
        titles = {int(t["id"]): (t["title"], TaskClass(t["task_class"])) for t in self.db.select("tasks")}
        out = []
        for r in rows:
            s = row_to_model(StudySession, r)
            title, klass = titles.get(s.task_id, ("?", TaskClass.DEADLINE_TASK))
            out.append(SessionView(s, title, klass))
        return out

    def get_session(self, session_id: int) -> SessionView | None:
        row = self.db.get("study_sessions", session_id)
        if not row:
            return None
        s = row_to_model(StudySession, row)
        t = self.db.get("tasks", s.task_id)
        return SessionView(s, t["title"] if t else "?", TaskClass(t["task_class"]) if t else TaskClass.DEADLINE_TASK)

    def complete_session(self, session_id: int, actual_minutes: int,
                         results: Mapping[int, RecallResult] | None = None,
                         finished: bool = False, now: datetime | None = None) -> None:
        """Record the Actual Result of a session.

        remaining_duration -= actual_minutes (or 0 if `finished`).  A REVIEW that reaches
        0 needs one RecallResult per topic; it updates MemoryState and the next review task.
        """
        if actual_minutes <= 0:
            raise ValueError("gerçek süre 0'dan büyük olmalı")
        now = now or datetime.now()
        with self.db.transaction():
            srow = self.db.get("study_sessions", session_id)
            if not srow:
                raise ValueError("session not found")
            session = row_to_model(StudySession, srow)
            if session.status is SessionStatus.COMPLETED:
                raise ValueError("oturum zaten tamamlanmış")
            task = self.get_task(session.task_id)
            if task is None:
                raise ValueError("task not found")
            occ_row = self.db.get("task_occurrences", session.occurrence_id) if session.occurrence_id else None
            current = int(occ_row["remaining_duration"]) if occ_row else int(task.remaining_duration or 0)
            new_remaining = 0 if finished else max(0, current - actual_minutes)

            objective: float | None = None
            rating: int | None = None
            if task.task_class is TaskClass.REVIEW and new_remaining == 0:
                results = results or {}
                missing = [t for t in task.topic_ids if t not in results]
                if missing:
                    raise ValueError("review tamamlamak için her konunun hatırlama sonucu gerekli")
                objective = sum(results[t].objective_score for t in task.topic_ids) / len(task.topic_ids)
                rating = round(sum(results[t].subjective_rating for t in task.topic_ids) / len(task.topic_ids))

            self.db.update("study_sessions", session_id, {
                "status": SessionStatus.COMPLETED.value, "actual_minutes": actual_minutes,
                "objective_score": objective, "subjective_rating": rating,
                "completed_at": _encode(now.replace(microsecond=0))})

            done = TaskStatus.COMPLETED.value
            if occ_row:
                self.db.update("task_occurrences", occ_row["id"], {
                    "remaining_duration": new_remaining,
                    **({"status": done} if new_remaining == 0 else {})})
            else:
                self.db.update("tasks", task.id, {
                    "remaining_duration": new_remaining, "updated_at": _encode(now.replace(microsecond=0)),
                    **({"status": done} if new_remaining == 0 else {})})

            if task.task_class is TaskClass.REVIEW and new_remaining == 0 and results:
                for tid in task.topic_ids:
                    mrow = self.db.get("memory_states", tid, key="topic_id")
                    if mrow is None:
                        continue
                    updated = self.memory.apply_review(row_to_model(MemoryState, mrow), results[tid], now.date())
                    self.db.upsert("memory_states", model_to_row(updated), conflict="topic_id")
                    self._sync_review_task(tid)

    def skip_session(self, session_id: int) -> None:
        self.db.update("study_sessions", session_id, {"status": SessionStatus.SKIPPED.value})