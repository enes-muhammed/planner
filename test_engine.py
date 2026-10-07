"""Tests for database.py + engine.py.  Run:  python -m unittest -v   (or: pytest)"""
from __future__ import annotations

import math
import sqlite3
import unittest
from dataclasses import replace
from datetime import date, datetime, time, timedelta

import engine as E
from database import Database
from engine import (AvailabilityBlock, AvailabilityType as AT, BusyInterval, EngineConfig, Exam,
                    MemoryConfig, MemoryEngine, MemoryPhase, PlannerService, RecallResult,
                    RecurrenceKind, RecurringRule, ReviewSource, Scheduler, SchedulerConfig,
                    SchedulerInput, SlotKind, TaskClass, TaskEngine, TaskStatus, UnscheduledReason)

TODAY = date(2026, 10, 7)  # Wednesday


# ------------------------------------------------------------------ helpers
def av(day: date, start="17:00", end="22:00", kind=AT.PRIMARY) -> AvailabilityBlock:
    return AvailabilityBlock(day, time.fromisoformat(start), time.fromisoformat(end), kind)


def days_av(n=14, start="17:00", end="22:00", kind=AT.PRIMARY):
    return [av(TODAY + timedelta(days=i), start, end, kind) for i in range(n)]


def dl(tid, title="Ödev", dur=90, deadline=TODAY + timedelta(days=10), priority=5, **kw):
    t = TaskEngine().deadline_task(title=title, duration=dur, deadline=deadline, priority=priority, **kw)
    t.id = tid
    return t


def rv(tid, ideal, topics=(1,), dur=30, urgency=7.0):
    t = TaskEngine().manual_review(f"Tekrar {tid}", topics, ideal, duration=dur)
    t.id, t.urgency = tid, urgency
    return t


def run(tasks, availability, occurrences=(), exams=(), busy=(), cfg=None, now_minute=0):
    return Scheduler(cfg or SchedulerConfig()).schedule(SchedulerInput(
        today=TODAY, now_minute=now_minute, tasks=list(tasks), occurrences=list(occurrences),
        availability=list(availability), busy=list(busy), exams=list(exams)))


def minutes_of(plan, task_id):
    return sum(s.minutes for s in plan.sessions if s.task_id == task_id)


def sig(plan):
    return [(s.task_id, s.occurrence_id, s.day, s.start_min, s.end_min, s.kind) for s in plan.sessions]


class SchedulerAssertions(unittest.TestCase):
    def assertNoOverlap(self, plan):
        by_day = {}
        for s in plan.sessions:
            by_day.setdefault(s.day, []).append(s)
        for sessions in by_day.values():
            sessions.sort(key=lambda s: s.start_min)
            for a, b in zip(sessions, sessions[1:]):
                self.assertLessEqual(a.end_min, b.start_min, "sessions overlap")


# ====================================================================== MEMORY
class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.m = MemoryEngine()

    def test_subjective_normalization(self):
        self.assertEqual(self.m.subjective_score(1), 0.0)
        self.assertEqual(self.m.subjective_score(10), 1.0)
        self.assertAlmostEqual(self.m.subjective_score(5), 4 / 9)
        for bad in (0, 11, -3):
            with self.assertRaises(ValueError):
                self.m.subjective_score(bad)

    def test_combined_score(self):
        self.assertAlmostEqual(self.m.combined_score(0.9, 8), 0.75 * 0.9 + 0.25 * (7 / 9))
        self.assertAlmostEqual(self.m.combined_score(1.0, 10), 1.0)
        self.assertAlmostEqual(self.m.combined_score(0.0, 1), 0.0)
        with self.assertRaises(ValueError):
            self.m.combined_score(1.2, 5)

    def test_weights_are_configurable(self):
        m = MemoryEngine(MemoryConfig(objective_weight=0.5, subjective_weight=0.5))
        self.assertAlmostEqual(m.combined_score(1.0, 1), 0.5)

    def test_multiplier_bands(self):
        cases = {0.0: 0.5, 0.39: 0.5, 0.40: 0.8, 0.59: 0.8, 0.60: 1.2, 0.79: 1.2,
                 0.80: 1.6, 0.89: 1.6, 0.90: 2.0, 1.0: 2.0}
        for q, mult in cases.items():
            self.assertEqual(self.m.performance_multiplier(q), mult, q)

    def test_stability_update(self):
        q = self.m.combined_score(0.9, 8)                      # 0.8694 -> x1.6
        self.assertAlmostEqual(self.m.update_stability(3.0, q, 0.5), 3.0 * 1.6 * (1.10 - 0.10))

    def test_stability_clamped(self):
        self.assertEqual(self.m.update_stability(1.0, 0.0, 0.5), 1.0)       # lower bound
        self.assertEqual(self.m.update_stability(170.0, 1.0, 0.0), 180.0)   # upper bound

    def test_difficulty_update(self):
        self.assertAlmostEqual(self.m.update_difficulty(0.5, 0.9), 0.5 + 0.1 * (0.5 - 0.9))
        self.assertAlmostEqual(self.m.update_difficulty(0.5, 0.1), 0.54)
        self.assertEqual(self.m.update_difficulty(0.99, 0.0), 1.0)
        self.assertEqual(self.m.update_difficulty(0.01, 1.0), 0.0)
        self.assertAlmostEqual(self.m.difficulty_factor(0.5), 1.0)

    def test_target_recall_interval(self):
        self.assertAlmostEqual(self.m.ideal_interval_days(1.0), 0.234465, places=5)
        self.assertAlmostEqual(self.m.ideal_interval_days(10.0), 2.34465, places=4)
        s = 25.0
        self.assertAlmostEqual(MemoryEngine.retrievability(s, self.m.ideal_interval_days(s)), 0.85)

    def test_other_target_recall(self):
        m = MemoryEngine(MemoryConfig(target_recall=0.5))
        self.assertAlmostEqual(m.ideal_interval_days(7.0), 7.0)   # half-life

    def test_minimum_interval(self):
        self.assertEqual(self.m.interval_days(3.0), 1)            # 0.70 d -> min 1 d
        self.assertEqual(self.m.interval_days(1.0), 1)
        self.assertEqual(self.m.interval_days(100.0), 23)         # 23.4 d
        m = MemoryEngine(MemoryConfig(min_interval_days=2))
        self.assertEqual(m.interval_days(3.0), 2)

    def test_initial_state(self):
        st = self.m.initial_state(1, TODAY)
        self.assertEqual((st.stability_days, st.difficulty, st.phase), (3.0, 0.5, MemoryPhase.NEW))
        self.assertEqual(st.next_review_date, TODAY + timedelta(days=1))

    def test_failed_recall_relearning(self):
        st = self.m.initial_state(1, TODAY)
        st = replace(st, stability_days=20.0)
        out = self.m.apply_review(st, RecallResult(0.1, 2), TODAY + timedelta(days=5))
        self.assertEqual(out.phase, MemoryPhase.RELEARNING)
        self.assertEqual(out.lapse_count, 1)
        self.assertLess(out.stability_days, 20.0)
        self.assertGreater(out.difficulty, 0.5)
        self.assertEqual(out.next_review_date, TODAY + timedelta(days=6))     # relearning interval
        again = self.m.apply_review(out, RecallResult(0.9, 9), TODAY + timedelta(days=6))
        self.assertEqual(again.phase, MemoryPhase.REVIEW)
        self.assertEqual(again.lapse_count, 1)

    def test_strong_recall(self):
        st = replace(self.m.initial_state(1, TODAY), stability_days=40.0)
        out = self.m.apply_review(st, RecallResult(1.0, 10), TODAY)
        self.assertEqual(out.phase, MemoryPhase.REVIEW)
        self.assertGreater(out.stability_days, 40.0 * 1.9)
        self.assertLess(out.difficulty, 0.5)
        self.assertGreater(out.next_review_date - TODAY, timedelta(days=15))
        self.assertEqual(out.review_count, 1)

    def test_invalid_config(self):
        with self.assertRaises(ValueError):
            MemoryConfig(target_recall=1.0)
        with self.assertRaises(ValueError):
            MemoryConfig(stability_min_days=5, stability_max_days=1)

    def test_review_window_never_before_min_interval(self):
        earliest, latest = self.m.review_window(TODAY + timedelta(days=1), TODAY)
        self.assertEqual(earliest, TODAY + timedelta(days=1))
        self.assertEqual(latest, TODAY + timedelta(days=2))


# ======================================================================== TASKS
class TaskTests(unittest.TestCase):
    def setUp(self):
        self.te = TaskEngine()

    def test_review_generation_from_memory(self):
        st = self.te.memory.initial_state(7, TODAY)
        topic = E.Topic(name="Üçgenler", subject_id=1, id=7)
        t = self.te.review_from_memory(st, topic)
        self.assertEqual(t.task_class, TaskClass.REVIEW)
        self.assertEqual(t.review_source, ReviewSource.AUTOMATIC)
        self.assertEqual(t.topic_ids, [7])
        self.assertEqual(t.ideal_date, st.next_review_date)
        self.assertLessEqual(t.earliest_date, t.ideal_date)
        self.assertGreaterEqual(t.latest_date, t.ideal_date)
        self.assertEqual(t.remaining_duration, t.duration)

    def test_manual_multi_topic_review(self):
        t = self.te.manual_review("Karma", [1, 2, 3, 3], TODAY + timedelta(days=3))
        self.assertEqual(t.topic_ids, [1, 2, 3])
        self.assertEqual(t.duration, 30 + 15 * 2)
        self.assertEqual(t.review_source, ReviewSource.MANUAL)
        with self.assertRaises(ValueError):
            self.te.manual_review("x", [], TODAY)

    def test_deadline_task(self):
        t = self.te.deadline_task("Matematik performans ödevi", 90, date(2026, 10, 17), priority=6,
                                  splittable=True, minimum_session=30)
        self.assertEqual((t.duration, t.remaining_duration, t.minimum_session), (90, 90, 30))
        self.assertTrue(t.splittable)
        t2 = self.te.deadline_task("x", 40, TODAY, splittable=False)
        self.assertEqual(t2.minimum_session, 40)

    def test_invalid_tasks(self):
        with self.assertRaises(ValueError):
            self.te.deadline_task("sıfır", 0, TODAY)
        with self.assertRaises(ValueError):
            self.te.deadline_task("negatif", -5, TODAY)
        with self.assertRaises(ValueError):
            self.te.deadline_task("öncelik", 30, TODAY, priority=11)
        with self.assertRaises(ValueError):
            self.te.deadline_task("  ", 30, TODAY)

    def test_recurring_daily_and_weekdays(self):
        t = self.te.recurring_task("Paragraf", 20, RecurringRule(RecurrenceKind.DAILY))
        occ = self.te.generate_occurrences(t, 1, TODAY, TODAY + timedelta(days=6))
        self.assertEqual(len(occ), 7)
        self.assertTrue(all(o.earliest_date == o.latest_date == o.occurrence_date for o in occ))
        mwf = self.te.recurring_task("Soru", 45, RecurringRule(RecurrenceKind.WEEKDAYS, weekdays=(0, 2, 4)))
        occ = self.te.generate_occurrences(mwf, 2, TODAY, TODAY + timedelta(days=13))
        self.assertEqual({o.occurrence_date.weekday() for o in occ}, {0, 2, 4})
        self.assertEqual(len(occ), 6)

    def test_recurring_times_per_week(self):
        t = self.te.recurring_task("Soru", 45, RecurringRule(RecurrenceKind.TIMES_PER_WEEK, times_per_week=3))
        mon = date(2026, 10, 5)
        occ = self.te.generate_occurrences(t, 1, mon, mon + timedelta(days=6))
        self.assertEqual([o.occurrence_date.weekday() for o in occ], [0, 2, 4])
        self.assertTrue(all(o.earliest_date == mon and o.latest_date == mon + timedelta(days=6) for o in occ))

    def test_recurring_respects_rule_dates(self):
        rule = RecurringRule(RecurrenceKind.DAILY, start_date=TODAY + timedelta(days=2),
                             end_date=TODAY + timedelta(days=4))
        t = self.te.recurring_task("x", 10, rule)
        self.assertEqual(len(self.te.generate_occurrences(t, 1, TODAY, TODAY + timedelta(days=30))), 3)
        with self.assertRaises(ValueError):
            RecurringRule(RecurrenceKind.WEEKDAYS)

    def test_split_duration(self):
        self.assertEqual(self.te.split_duration(90, 30, 120), [90])
        self.assertEqual(self.te.split_duration(300, 30, 120), [100, 100, 100])
        chunks = self.te.split_duration(250, 60, 120)
        self.assertEqual(sum(chunks), 250)
        self.assertTrue(all(60 <= c <= 120 for c in chunks))
        self.assertEqual(self.te.split_duration(10, 30, 120), [10])
        with self.assertRaises(ValueError):
            self.te.split_duration(0, 30, 120)

    def test_overdue_flag(self):
        t = dl(1, deadline=TODAY - timedelta(days=1))
        self.assertTrue(t.is_overdue(TODAY))
        t.status = TaskStatus.COMPLETED
        self.assertFalse(t.is_overdue(TODAY))


# ===================================================================== SCHEDULER
class SchedulerTests(SchedulerAssertions):
    def test_deadline_task_scheduled_before_deadline(self):
        plan = run([dl(1, dur=90, deadline=TODAY + timedelta(days=3))], days_av())
        self.assertEqual(minutes_of(plan, 1), 90)
        self.assertTrue(all(s.day <= TODAY + timedelta(days=3) for s in plan.sessions))
        self.assertTrue(all(s.explanation for s in plan.sessions))
        self.assertEqual(plan.unscheduled, [])

    def test_task_splitting_respects_minimum_session(self):
        blocks = [av(TODAY, "17:00", "17:50"), av(TODAY, "19:00", "19:50")]
        cfg = SchedulerConfig(buffer_fraction=0.0)
        t = dl(1, dur=90, deadline=TODAY, splittable=True, minimum_session=30)
        plan = run([t], blocks, cfg=cfg)
        self.assertEqual(minutes_of(plan, 1), 90)
        self.assertEqual(len(plan.sessions), 2)
        self.assertTrue(all(s.minutes >= 30 for s in plan.sessions))
        self.assertNoOverlap(plan)

    def test_non_splittable_stays_whole(self):
        plan = run([dl(1, dur=60, splittable=False)], days_av())
        self.assertEqual([s.minutes for s in plan.sessions], [60])

    def test_max_session_for_long_splittable(self):
        plan = run([dl(1, dur=300, deadline=TODAY + timedelta(days=6), splittable=True)], days_av())
        self.assertEqual(minutes_of(plan, 1), 300)
        self.assertTrue(all(s.minutes <= 120 for s in plan.sessions))

    def test_primary_before_reserve(self):
        blocks = days_av(3) + days_av(3, "22:00", "23:30", AT.RESERVE)
        plan = run([dl(1, dur=120, deadline=TODAY + timedelta(days=2))], blocks)
        self.assertEqual(minutes_of(plan, 1), 120)
        self.assertTrue(all(s.kind is SlotKind.PRIMARY for s in plan.sessions))

    def test_reserve_used_only_when_needed(self):
        # primary: 2 x 60 min (12 min buffer each); task of 200 min due in 1 day needs the reserve
        blocks = days_av(2, "17:00", "18:00") + days_av(2, "21:00", "23:00", AT.RESERVE)
        plan = run([dl(1, dur=200, deadline=TODAY + timedelta(days=1), splittable=True)], blocks)
        kinds = {s.kind for s in plan.sessions}
        self.assertIn(SlotKind.RESERVE, kinds)
        self.assertEqual(minutes_of(plan, 1), 200)

    def test_only_reserve_available(self):
        blocks = days_av(3, "21:00", "23:00", AT.RESERVE)
        plan = run([dl(1, dur=60, deadline=TODAY + timedelta(days=2)), rv(2, TODAY + timedelta(days=1))], blocks)
        self.assertEqual(minutes_of(plan, 1), 60)                 # deadline may use reserve
        self.assertTrue(all(s.kind is SlotKind.RESERVE for s in plan.sessions))
        self.assertEqual(minutes_of(plan, 2), 0)                  # review may not
        self.assertEqual([u.task_id for u in plan.unscheduled], [2])

    def test_unavailable_overrides_primary(self):
        blocks = [av(TODAY, "17:00", "21:00"), av(TODAY, "18:00", "19:00", AT.UNAVAILABLE)]
        plan = run([dl(1, dur=120, deadline=TODAY, splittable=True, minimum_session=30)], blocks,
                   cfg=SchedulerConfig(buffer_fraction=0.0))
        for s in plan.sessions:
            self.assertFalse(s.start_min < 19 * 60 and s.end_min > 18 * 60)
        self.assertEqual(minutes_of(plan, 1), 120)

    def test_buffer_preserved(self):
        blocks = days_av(3)                                       # 300 min/day, 60 buffer
        plan = run([dl(1, dur=500, deadline=TODAY + timedelta(days=10), splittable=True)], blocks)
        self.assertEqual(minutes_of(plan, 1), 500)
        for st in plan.day_stats.values():
            self.assertEqual(st.buffer_minutes, 60 if st.primary_capacity else 0)
            self.assertEqual(st.planned_buffer, 0)
            self.assertLessEqual(st.planned_primary, 240)

    def test_buffer_used_only_in_emergency(self):
        blocks = [av(TODAY, "17:00", "19:00")]                    # 96 primary + 24 buffer
        urgent = dl(1, dur=100, deadline=TODAY, splittable=True, minimum_session=20)
        plan = run([urgent], blocks)
        self.assertEqual(minutes_of(plan, 1), 100)
        self.assertIn(SlotKind.BUFFER, {s.kind for s in plan.sessions})
        # a review for the same capacity must never touch the buffer
        plan2 = run([rv(1, TODAY, dur=110)], blocks)
        self.assertEqual(plan2.sessions, [])

    def test_deadline_urgency_beats_priority_label(self):
        # low-priority homework due tomorrow vs. high-priority routine; capacity is tight
        blocks = days_av(2, "17:00", "19:00")
        homework = dl(1, "Performans", dur=90, deadline=TODAY + timedelta(days=1), priority=2, splittable=False)
        occ = E.TaskOccurrence(task_id=2, occurrence_date=TODAY, duration=60, id=1,
                               earliest_date=TODAY, latest_date=TODAY)
        routine = TaskEngine().recurring_task("TYT Matematik", 60, RecurringRule(RecurrenceKind.DAILY), priority=9)
        routine.id = 2
        plan = run([homework, routine], blocks, occurrences=[occ])
        self.assertEqual(minutes_of(plan, 1), 90)
        self.assertTrue(all(s.day <= TODAY + timedelta(days=1) for s in plan.sessions if s.task_id == 1))
        self.assertNoOverlap(plan)

    def test_deadline_today_and_in_the_past(self):
        plan = run([dl(1, dur=60, deadline=TODAY)], days_av(3))
        self.assertTrue(all(s.day == TODAY for s in plan.sessions))
        self.assertEqual(minutes_of(plan, 1), 60)
        late = run([dl(1, dur=60, deadline=TODAY - timedelta(days=2))], days_av(3))
        self.assertEqual(minutes_of(late, 1), 60)
        self.assertTrue(all(s.day == TODAY for s in late.sessions))
        self.assertIn("GECİKMİŞ", late.sessions[0].explanation)

    def test_now_cuts_today(self):
        plan = run([dl(1, dur=60, deadline=TODAY)], days_av(1), now_minute=20 * 60)
        self.assertTrue(all(s.start_min >= 20 * 60 for s in plan.sessions))
        full = run([dl(1, dur=200, deadline=TODAY, splittable=True)], days_av(1), now_minute=21 * 60)
        self.assertLess(minutes_of(full, 1), 200)
        self.assertTrue(any(u.task_id == 1 for u in full.unscheduled))

    def test_review_on_ideal_date_when_free(self):
        ideal = TODAY + timedelta(days=3)
        plan = run([rv(1, ideal)], days_av())
        self.assertEqual(plan.sessions[0].day, ideal)
        self.assertIn("sapma +0", plan.sessions[0].explanation)

    def test_review_moves_within_window_when_ideal_day_unavailable(self):
        ideal = TODAY + timedelta(days=3)
        blocks = [b for b in days_av() if b.block_date != ideal]
        plan = run([rv(1, ideal)], blocks)
        dev = (plan.sessions[0].day - ideal).days
        self.assertEqual(abs(dev), 1)                             # inside +-1 day window
        self.assertIn("ideal günde uygun boşluk yok", plan.sessions[0].explanation)

    def test_review_prefers_ideal_date_over_load_balancing(self):
        ideal = TODAY + timedelta(days=2)
        plan = run([rv(1, ideal), dl(2, dur=60, deadline=ideal)], days_av())
        self.assertEqual([s.day for s in plan.sessions if s.task_id == 1], [ideal])

    def test_exam_pulls_review_forward(self):
        ideal = TODAY + timedelta(days=8)
        exam = Exam(title="Mat sınavı", exam_date=TODAY + timedelta(days=5), id=1, topic_ids=[1])
        plan = run([rv(1, ideal, topics=(1,))], days_av(), exams=[exam])
        self.assertLessEqual(plan.sessions[0].day, exam.exam_date)

    def test_recurring_routine_preserved_daily(self):
        t = TaskEngine().recurring_task("Paragraf", 20, RecurringRule(RecurrenceKind.DAILY), priority=5)
        t.id = 1
        occs = TaskEngine().generate_occurrences(t, 1, TODAY, TODAY + timedelta(days=6))
        for i, o in enumerate(occs, start=1):
            o.id = i
        plan = run([t], days_av(7), occurrences=occs)
        self.assertEqual(sorted(s.day for s in plan.sessions), [o.occurrence_date for o in occs])

    def test_recurring_window_expired(self):
        t = TaskEngine().recurring_task("Paragraf", 20, RecurringRule(RecurrenceKind.DAILY))
        t.id = 1
        o = E.TaskOccurrence(task_id=1, occurrence_date=TODAY - timedelta(days=1), duration=20, id=1,
                             earliest_date=TODAY - timedelta(days=1), latest_date=TODAY - timedelta(days=1))
        plan = run([t], days_av(), occurrences=[o])
        self.assertEqual(plan.unscheduled[0].reason, UnscheduledReason.WINDOW_EXPIRED)

    def test_weekly_flexible_recurring_spreads_over_week(self):
        t = TaskEngine().recurring_task("Soru", 45, RecurringRule(RecurrenceKind.TIMES_PER_WEEK, times_per_week=3))
        t.id = 1
        mon = date(2026, 10, 5)
        occs = TaskEngine().generate_occurrences(t, 1, mon, mon + timedelta(days=6))
        for i, o in enumerate(occs, start=1):
            o.id = i
        plan = run([t], days_av(7), occurrences=[o for o in occs if o.occurrence_date >= TODAY])
        days = [s.day for s in plan.sessions]
        self.assertEqual(len(days), len(set(days)))               # one per day
        self.assertTrue(all(TODAY <= d <= mon + timedelta(days=6) for d in days))

    # ---- edge cases ----
    def test_no_availability_at_all(self):
        plan = run([dl(1), rv(2, TODAY + timedelta(days=1))], [])
        self.assertEqual(plan.sessions, [])
        self.assertTrue(all(u.reason is UnscheduledReason.NO_AVAILABILITY for u in plan.unscheduled))
        self.assertTrue(plan.warnings)

    def test_task_fits_no_slot(self):
        blocks = [av(TODAY, "17:00", "18:30"), av(TODAY, "20:00", "21:30")]
        plan = run([dl(1, dur=100, deadline=TODAY, splittable=False)], blocks,
                   cfg=SchedulerConfig(buffer_fraction=0.0))
        self.assertEqual(plan.sessions, [])
        self.assertEqual(plan.unscheduled[0].reason, UnscheduledReason.NO_CONTIGUOUS_SLOT)
        big = run([rv(1, TODAY + timedelta(days=1), dur=150)], days_av(1, "17:00", "19:00"))
        self.assertEqual(big.unscheduled[0].reason, UnscheduledReason.INSUFFICIENT_CAPACITY)

    def test_extremely_long_task_reports_shortfall(self):
        t = dl(1, dur=5000, deadline=TODAY + timedelta(days=5), splittable=True)
        plan = run([t], days_av())
        self.assertGreater(minutes_of(plan, 1), 0)
        self.assertLess(minutes_of(plan, 1), 5000)
        self.assertEqual(minutes_of(plan, 1) + plan.unscheduled[0].minutes, 5000)
        self.assertTrue(any("Son tarih riski" in w for w in plan.warnings))
        self.assertNoOverlap(plan)

    def test_zero_remaining_is_ignored(self):
        t = dl(1)
        t.remaining_duration = 0
        self.assertEqual(run([t], days_av()).sessions, [])

    def test_review_backlog_is_spread_and_does_not_starve_deadlines(self):
        reviews = [rv(i, TODAY - timedelta(days=i % 3), topics=(i,), urgency=5 + (i % 4)) for i in range(1, 81)]
        homework = dl(100, dur=120, deadline=TODAY + timedelta(days=2), splittable=True)
        plan = run(reviews + [homework], days_av())
        self.assertEqual(minutes_of(plan, 100), 120)
        per_day = {}
        for s in plan.sessions:
            if s.task_class is TaskClass.REVIEW:
                per_day[s.day] = per_day.get(s.day, 0) + s.minutes
        self.assertTrue(per_day)
        self.assertTrue(all(v <= 120 for v in per_day.values()))   # 50% of 240 usable minutes
        self.assertTrue(any(u.task_id != 100 for u in plan.unscheduled))   # excess is reported
        self.assertNoOverlap(plan)

    def test_multiple_tasks_same_topic(self):
        a, b = rv(1, TODAY + timedelta(days=1), topics=(5,)), rv(2, TODAY + timedelta(days=1), topics=(5,))
        c = dl(3, dur=45, deadline=TODAY + timedelta(days=3))
        c.topic_ids = [5]
        plan = run([a, b, c], days_av())
        self.assertEqual({s.task_id for s in plan.sessions}, {1, 2, 3})
        self.assertNoOverlap(plan)

    def test_multi_topic_review(self):
        t = TaskEngine().manual_review("Karma", [1, 2, 3], TODAY + timedelta(days=2))
        t.id = 1
        plan = run([t], days_av())
        self.assertEqual(minutes_of(plan, 1), 60)

    def test_deterministic(self):
        tasks = [dl(1, dur=200, splittable=True), dl(2, "B", dur=80, priority=8),
                 rv(3, TODAY + timedelta(days=1)), rv(4, TODAY + timedelta(days=1), topics=(2,))]
        first = run(tasks, days_av())
        again = run(tasks, days_av())
        shuffled = run(list(reversed(tasks)), list(reversed(days_av())))
        self.assertEqual(sig(first), sig(again))
        self.assertEqual(sig(first), sig(shuffled))

    def test_new_deadline_task_is_protected(self):
        blocks = days_av(2, "17:00", "19:00")                     # 96 primary + 24 buffer per day
        base = [dl(1, "Düşük", dur=90, deadline=TODAY + timedelta(days=1), priority=2, splittable=False)]
        before = run(base, blocks)
        urgent = dl(2, "Acil", dur=60, deadline=TODAY, priority=9, splittable=False)
        after = run(base + [urgent], blocks)
        self.assertEqual(minutes_of(after, 2), 60)
        self.assertTrue(all(s.day == TODAY for s in after.sessions if s.task_id == 2))
        self.assertEqual(minutes_of(after, 1), 90)                # low-priority task moved, not lost
        self.assertNotEqual(sig(before), sig(after))
        self.assertNoOverlap(after)

    def test_busy_intervals_are_respected(self):
        busy = [BusyInterval(TODAY, 17 * 60, 20 * 60)]
        plan = run([dl(1, dur=60, deadline=TODAY)], days_av(1), busy=busy)
        self.assertTrue(all(s.start_min >= 20 * 60 for s in plan.sessions))


# ================================================================ DATABASE/SERVICE
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()

    def test_foreign_keys_and_version(self):
        self.assertTrue(self.db.foreign_keys_enabled())
        self.assertEqual(self.db.schema_version(), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.insert("topics", {"subject_id": 999, "name": "x", "created_at": "2026-01-01T00:00:00"})

    def test_schema_matches_models(self):
        pairs = {"students": E.Student, "subjects": E.Subject, "topics": E.Topic,
                 "learning_events": E.LearningEvent, "memory_states": E.MemoryState, "tasks": E.Task,
                 "task_occurrences": E.TaskOccurrence, "availability_blocks": E.AvailabilityBlock,
                 "study_sessions": E.StudySession, "exams": E.Exam, "school_timetable": E.SchoolTimetableEntry}
        for table, cls in pairs.items():
            self.assertEqual(set(E.column_names(cls)), set(self.db.table_columns(table)), table)

    def test_identifier_validation_and_injection(self):
        with self.assertRaises(ValueError):
            self.db.select("tasks; DROP TABLE tasks")
        with self.assertRaises(ValueError):
            self.db.select("tasks", {"nope": 1})
        self.db.insert("students", {"name": "x'); DROP TABLE students;--", "created_at": "2026-01-01T00:00:00"})
        self.assertEqual(len(self.db.select("students")), 1)

    def test_transaction_rollback(self):
        with self.assertRaises(RuntimeError):
            with self.db.transaction():
                self.db.insert("students", {"name": "a", "created_at": "x"})
                raise RuntimeError
        self.assertEqual(self.db.select("students"), [])
        with self.db.transaction():
            self.db.insert("students", {"name": "a", "created_at": "x"})
            with self.assertRaises(RuntimeError):
                with self.db.transaction():
                    self.db.insert("students", {"name": "b", "created_at": "x"})
                    raise RuntimeError
        self.assertEqual([r["name"] for r in self.db.select("students")], ["a"])

    def test_zero_duration_rejected_by_schema(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.insert("tasks", {"student_id": 1, "task_class": "DEADLINE_TASK", "title": "x", "duration": 0,
                                     "remaining_duration": 0, "priority": 5, "created_at": "x", "updated_at": "x"})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.sv = PlannerService(self.db)
        self.subj = self.sv.add_subject("Matematik")

    def _availability(self, days=14):
        self.sv.add_availability_range(TODAY, TODAY + timedelta(days=days - 1), range(7),
                                       time(17), time(22), AT.PRIMARY)

    def test_chain_event_to_review_to_session(self):
        ev = self.sv.add_learning_event(self.subj.id, TODAY, "Üçgenler", 1, 2, "ilk ders")
        self.assertEqual(len(self.sv.list_learning_events(self.subj.id)), 1)
        reviews = self.sv.list_tasks("review", TODAY)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].ideal_date, TODAY + timedelta(days=1))
        self.assertEqual(reviews[0].topic_ids, [ev.topic_id])
        self._availability()
        plan = self.sv.replan(datetime(2026, 10, 7, 12, 0))
        self.assertEqual(plan.sessions[0].day, TODAY + timedelta(days=1))
        sessions = self.sv.list_sessions(TODAY, TODAY + timedelta(days=3))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].session.status, E.SessionStatus.PLANNED)

    def test_events_are_chronological_and_topics_reused(self):
        for d, p, name in [(14, (1, 2), "Trigonometri"), (7, (1, 2), "Üçgenler"), (9, (3, 4), "Trigonometri")]:
            self.sv.add_learning_event(self.subj.id, date(2026, 1, d), name, *p)
        events = self.sv.list_learning_events(self.subj.id)
        self.assertEqual([e.event.event_date.day for e in events], [7, 9, 14])
        self.assertEqual(len(self.sv.list_topics(self.subj.id)), 2)
        self.assertEqual(len(self.sv.list_tasks("review", TODAY)), 2)       # no duplicate auto reviews
        with self.assertRaises(ValueError):
            self.sv.add_learning_event(self.subj.id, TODAY, "x", 4, 3)

    def test_review_completion_updates_memory_and_next_review(self):
        ev = self.sv.add_learning_event(self.subj.id, TODAY, "Üçgenler")
        self._availability()
        self.sv.replan(datetime(2026, 10, 7, 12, 0))
        s = self.sv.list_sessions(TODAY, TODAY + timedelta(days=5))[0].session
        with self.assertRaises(ValueError):                              # result required
            self.sv.complete_session(s.id, 30)
        self.sv.complete_session(s.id, 30, {ev.topic_id: RecallResult(0.9, 8)}, now=datetime(2026, 10, 8, 18))
        mem = self.sv.list_memory(self.subj.id)[0].state
        self.assertEqual(mem.review_count, 1)
        self.assertAlmostEqual(mem.stability_days, 4.8)
        pending = self.sv.list_tasks("review", TODAY)
        self.assertEqual(len(pending), 1)
        self.assertGreaterEqual(pending[0].ideal_date, date(2026, 10, 9))
        self.assertEqual(len(self.sv.list_tasks("completed", TODAY)), 1)

    def test_failed_review_goes_to_relearning(self):
        ev = self.sv.add_learning_event(self.subj.id, TODAY, "Üçgenler")
        self._availability()
        self.sv.replan(datetime(2026, 10, 7, 12, 0))
        s = self.sv.list_sessions(TODAY, TODAY + timedelta(days=5))[0].session
        self.sv.complete_session(s.id, 30, {ev.topic_id: RecallResult(0.1, 2)}, now=datetime(2026, 10, 8, 18))
        self.assertEqual(self.sv.list_memory(self.subj.id)[0].state.phase, MemoryPhase.RELEARNING)

    def test_multi_topic_manual_review_completion(self):
        topics = [self.sv.add_learning_event(self.subj.id, TODAY, n).topic_id for n in ("A", "B", "C")]
        task = self.sv.add_manual_review(title="Karma", topic_ids=topics, ideal_date=TODAY + timedelta(days=2))
        self.assertEqual(self.sv.get_task(task.id).topic_ids, topics)
        self._availability()
        self.sv.replan(datetime(2026, 10, 7, 12, 0))
        sess = [v for v in self.sv.list_sessions(TODAY, TODAY + timedelta(days=5)) if v.session.task_id == task.id][0]
        with self.assertRaises(ValueError):                              # missing topic result
            self.sv.complete_session(sess.session.id, 60, {topics[0]: RecallResult(1, 9)})
        self.sv.complete_session(sess.session.id, 60, {t: RecallResult(1.0, 9) for t in topics},
                                 now=datetime(2026, 10, 9, 18))
        self.assertTrue(all(m.state.review_count == 1 for m in self.sv.list_memory(self.subj.id)))

    def test_replanning_after_actual_duration(self):
        self._availability(5)
        task = self.sv.add_deadline_task(title="Ödev", duration=90, deadline=TODAY + timedelta(days=3),
                                         priority=6, splittable=True, minimum_session=30)
        self.sv.replan(datetime(2026, 10, 7, 12, 0))
        first = self.sv.list_sessions(TODAY, TODAY + timedelta(days=4))[0].session
        planned = first.planned_minutes
        # student needed 60 min instead of the planned chunk
        self.sv.complete_session(first.id, 60, now=datetime(2026, 10, 7, 18, 30))
        self.assertEqual(self.sv.get_task(task.id).remaining_duration, 30)
        plan = self.sv.replan(datetime(2026, 10, 7, 18, 30))
        self.assertEqual(minutes_of(plan, task.id), 30)
        busy_end = 17 * 60 + 60
        for s in plan.sessions:                                          # completed time is not reused
            if s.day == TODAY:
                self.assertTrue(s.start_min >= busy_end or s.end_min <= 17 * 60)
        self.assertGreaterEqual(planned, 30)

    def test_missed_sessions_are_rescheduled(self):
        self._availability(5)
        task = self.sv.add_deadline_task(title="Ödev", duration=60, deadline=TODAY + timedelta(days=3),
                                         splittable=False)
        self.sv.replan(datetime(2026, 10, 7, 12, 0))
        plan = self.sv.replan(datetime(2026, 10, 7, 23, 0))             # evening passed, nothing done
        statuses = [v.session.status for v in self.sv.list_sessions(TODAY, TODAY + timedelta(days=4))]
        self.assertIn(E.SessionStatus.MISSED, statuses)
        self.assertEqual(minutes_of(plan, task.id), 60)
        self.assertTrue(all(s.day > TODAY for s in plan.sessions))

    def test_recurring_task_end_to_end(self):
        self._availability(10)
        task = self.sv.add_recurring_task(today=TODAY, title="20 paragraf", duration=20,
                                          rule=RecurringRule(RecurrenceKind.DAILY), priority=7)
        plan = self.sv.replan(datetime(2026, 10, 7, 12, 0))
        self.assertEqual(len([s for s in plan.sessions if s.task_id == task.id]), 10)
        occ = self.db.select("task_occurrences", {"task_id": task.id})
        self.assertGreaterEqual(len(occ), 14)
        first = self.sv.list_sessions(TODAY, TODAY)[0].session
        self.sv.complete_session(first.id, 20, now=datetime(2026, 10, 7, 18))
        self.assertEqual(self.sv.get_task(task.id).status, TaskStatus.PENDING)   # series continues
        plan2 = self.sv.replan(datetime(2026, 10, 7, 19, 0))
        self.assertEqual(len([s for s in plan2.sessions if s.task_id == task.id and s.day == TODAY]), 0)

    def test_delete_subject_cascades(self):
        self.sv.add_learning_event(self.subj.id, TODAY, "Üçgenler")
        self.sv.delete_subject(self.subj.id)
        self.assertEqual(self.db.select("topics"), [])
        self.assertEqual(self.db.select("memory_states"), [])
        self.assertEqual(self.db.select("tasks"), [])

    def test_config_override_persists(self):
        self.sv.update_config({"scheduler": {"buffer_fraction": 0.3}, "memory": {"target_recall": 0.9}})
        sv2 = PlannerService(self.db)
        self.assertEqual(sv2.config.scheduler.buffer_fraction, 0.3)
        self.assertEqual(sv2.memory.cfg.target_recall, 0.9)
        with self.assertRaises(ValueError):
            self.sv.update_config({"scheduler": {"buffer_fraction": 1.5}})

    def test_task_views_filter(self):
        self.sv.add_deadline_task(title="Geçmiş", duration=30, deadline=TODAY - timedelta(days=1))
        self.sv.add_deadline_task(title="Gelecek", duration=30, deadline=TODAY + timedelta(days=3))
        self.assertEqual([t.title for t in self.sv.list_tasks("overdue", TODAY)], ["Geçmiş"])
        self.assertEqual(len(self.sv.list_tasks("deadline", TODAY)), 2)
        self.assertEqual(self.sv.list_tasks("completed", TODAY), [])


if __name__ == "__main__":
    unittest.main()
