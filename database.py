"""database.py - SQLite persistence layer (standard library only, no ORM).

Responsibilities
----------------
* connection management (foreign keys ON, WAL for file databases)
* schema creation + versioned migrations (PRAGMA user_version)
* nested transactions (BEGIN / SAVEPOINT)
* all SQL of the application (engine.py never builds SQL itself)

Conventions
-----------
* Dates are stored as ``YYYY-MM-DD``, times as ``HH:MM``, datetimes as ISO 8601.
* Rows are returned as plain ``dict`` objects; engine.py maps them to dataclasses.
* Every value is passed through parameterized queries.  Table and column names
  (which cannot be parameterized) are validated against the live schema.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

# --------------------------------------------------------------------------- #
# Schema / migrations
# --------------------------------------------------------------------------- #

_V1 = """
CREATE TABLE students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE subjects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#4F7CAC',
    created_at  TEXT NOT NULL,
    UNIQUE (student_id, name)
);

CREATE TABLE topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (subject_id, name)
);

CREATE TABLE learning_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id      INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    event_date    TEXT NOT NULL,
    period_start  INTEGER,
    period_end    INTEGER,
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX idx_learning_events_topic ON learning_events(topic_id);
CREATE INDEX idx_learning_events_date  ON learning_events(event_date);

CREATE TABLE memory_states (
    topic_id               INTEGER PRIMARY KEY REFERENCES topics(id) ON DELETE CASCADE,
    stability_days         REAL NOT NULL,
    difficulty             REAL NOT NULL,
    phase                  TEXT NOT NULL CHECK (phase IN ('NEW','REVIEW','RELEARNING')),
    last_review_date       TEXT NOT NULL,
    next_review_date       TEXT NOT NULL,
    review_count           INTEGER NOT NULL DEFAULT 0,
    lapse_count            INTEGER NOT NULL DEFAULT 0,
    last_objective_score   REAL,
    last_subjective_score  REAL,
    last_combined_score    REAL,
    updated_at             TEXT NOT NULL
);

CREATE TABLE exams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id  INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    title       TEXT NOT NULL,
    exam_date   TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE exam_topic_links (
    exam_id   INTEGER NOT NULL REFERENCES exams(id)  ON DELETE CASCADE,
    topic_id  INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (exam_id, topic_id)
);

CREATE TABLE tasks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id          INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    task_class          TEXT NOT NULL CHECK (task_class IN ('REVIEW','DEADLINE_TASK','RECURRING_TASK')),
    title               TEXT NOT NULL,
    duration            INTEGER NOT NULL CHECK (duration > 0),
    remaining_duration  INTEGER NOT NULL CHECK (remaining_duration >= 0),
    priority            INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 10),
    deadline            TEXT,
    ideal_date          TEXT,
    earliest_date       TEXT,
    latest_date         TEXT,
    splittable          INTEGER NOT NULL DEFAULT 0,
    minimum_session     INTEGER NOT NULL DEFAULT 0,
    recurring_rule      TEXT,
    tags                TEXT NOT NULL DEFAULT '[]',
    review_source       TEXT CHECK (review_source IN ('AUTOMATIC','MANUAL')),
    status              TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','COMPLETED','CANCELLED','MISSED')),
    urgency             REAL NOT NULL DEFAULT 5.0,
    delay_cost          REAL NOT NULL DEFAULT 0.0,
    exam_id             INTEGER REFERENCES exams(id) ON DELETE SET NULL,
    notes               TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX idx_tasks_status ON tasks(status);

CREATE TABLE task_topic_links (
    task_id   INTEGER NOT NULL REFERENCES tasks(id)  ON DELETE CASCADE,
    topic_id  INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, topic_id)
);

CREATE TABLE task_occurrences (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id             INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    occurrence_date     TEXT NOT NULL,
    duration            INTEGER NOT NULL CHECK (duration > 0),
    earliest_date       TEXT,
    latest_date         TEXT,
    remaining_duration  INTEGER NOT NULL CHECK (remaining_duration >= 0),
    status              TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','COMPLETED','CANCELLED','MISSED')),
    UNIQUE (task_id, occurrence_date)
);

CREATE TABLE availability_blocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    block_date  TEXT NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    block_type  TEXT NOT NULL CHECK (block_type IN ('PRIMARY','RESERVE','UNAVAILABLE')),
    CHECK (start_time < end_time)
);
CREATE INDEX idx_availability_date ON availability_blocks(block_date);

CREATE TABLE study_sessions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id           INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    occurrence_id     INTEGER REFERENCES task_occurrences(id) ON DELETE CASCADE,
    session_date      TEXT NOT NULL,
    start_time        TEXT NOT NULL,
    end_time          TEXT NOT NULL,
    planned_minutes   INTEGER NOT NULL CHECK (planned_minutes > 0),
    actual_minutes    INTEGER,
    status            TEXT NOT NULL DEFAULT 'PLANNED'
                      CHECK (status IN ('PLANNED','COMPLETED','MISSED','SKIPPED')),
    slot_kind         TEXT NOT NULL DEFAULT 'PRIMARY' CHECK (slot_kind IN ('PRIMARY','BUFFER','RESERVE')),
    cost              REAL NOT NULL DEFAULT 0.0,
    explanation       TEXT NOT NULL DEFAULT '',
    objective_score   REAL,
    subjective_rating INTEGER,
    created_at        TEXT NOT NULL,
    completed_at      TEXT
);
CREATE INDEX idx_sessions_date ON study_sessions(session_date);

CREATE TABLE school_timetable (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    weekday     INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    period_no   INTEGER NOT NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE (student_id, weekday, period_no)
);

CREATE TABLE settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

_V2 = """
CREATE TABLE units (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    order_no    INTEGER NOT NULL DEFAULT 1,
    start_date  TEXT,
    end_date    TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (subject_id, name)
);
CREATE INDEX idx_units_subject ON units(subject_id);

ALTER TABLE topics ADD COLUMN unit_id INTEGER REFERENCES units(id) ON DELETE SET NULL;
CREATE INDEX idx_topics_unit ON topics(unit_id);
"""

_V3 = """
-- 1. Müfredat Hiyerarşisi: Alt Konular (Subtopics)
CREATE TABLE subtopics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id    INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    order_no    INTEGER NOT NULL DEFAULT 1,
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (topic_id, name)
);
CREATE INDEX idx_subtopics_topic ON subtopics(topic_id);

-- 2. Kazanımlar / Öğrenme Çıktıları (Learning Outcomes)
CREATE TABLE learning_outcomes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subtopic_id  INTEGER NOT NULL REFERENCES subtopics(id) ON DELETE CASCADE,
    code         TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL,
    order_no     INTEGER NOT NULL DEFAULT 1,
    is_covered   INTEGER NOT NULL DEFAULT 0,
    covered_at   TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_outcomes_subtopic ON learning_outcomes(subtopic_id);

-- 3. Öğrenme Etkinlikleri (Learning Events) ile Alt Konu ve Kazanım İlişkisi
ALTER TABLE learning_events ADD COLUMN subtopic_id INTEGER REFERENCES subtopics(id) ON DELETE SET NULL;
CREATE INDEX idx_learning_events_subtopic ON learning_events(subtopic_id);

CREATE TABLE learning_event_outcomes (
    event_id    INTEGER NOT NULL REFERENCES learning_events(id) ON DELETE CASCADE,
    outcome_id  INTEGER NOT NULL REFERENCES learning_outcomes(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, outcome_id)
);

-- 4. Alt Konu Düzeyinde Hafıza Durumu (FSRS Memory States)
CREATE TABLE subtopic_memory_states (
    subtopic_id            INTEGER PRIMARY KEY REFERENCES subtopics(id) ON DELETE CASCADE,
    stability_days         REAL NOT NULL,
    difficulty             REAL NOT NULL,
    phase                  TEXT NOT NULL CHECK (phase IN ('NEW','REVIEW','RELEARNING')),
    last_review_date       TEXT NOT NULL,
    next_review_date       TEXT NOT NULL,
    review_count           INTEGER NOT NULL DEFAULT 0,
    lapse_count            INTEGER NOT NULL DEFAULT 0,
    last_objective_score   REAL,
    last_subjective_score  REAL,
    last_combined_score    REAL,
    updated_at             TEXT NOT NULL
);

-- 5. Görev ve Sınavların Alt Konularla İlişkilendirilmesi
CREATE TABLE task_subtopic_links (
    task_id      INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    subtopic_id  INTEGER NOT NULL REFERENCES subtopics(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, subtopic_id)
);

CREATE TABLE exam_subtopic_links (
    exam_id      INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    subtopic_id  INTEGER NOT NULL REFERENCES subtopics(id) ON DELETE CASCADE,
    PRIMARY KEY (exam_id, subtopic_id)
);

-- 6. Akademik Dönemler ve Çeyrekler (4 Periyot, 2 Dönem)
CREATE TABLE academic_terms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    term_type   TEXT NOT NULL CHECK (term_type IN ('SEMESTER', 'QUARTER')),
    term_no     INTEGER NOT NULL,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_academic_terms_dates ON academic_terms(start_date, end_date);

-- 7. 2026–2027 MEB & Diyanet Okul Var / Yok / Tatil / Yarım Gün Takvimi
CREATE TABLE academic_calendar_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    start_date   TEXT NOT NULL,
    end_date     TEXT NOT NULL,
    day_status   TEXT NOT NULL CHECK (day_status IN ('OPEN', 'CLOSED', 'HALF_DAY', 'EXAM_PERIOD')),
    event_type   TEXT NOT NULL CHECK (event_type IN ('SEMESTER_START', 'SEMESTER_END', 'BREAK', 'HOLIDAY', 'EXAM', 'CUSTOM')),
    description  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_academic_cal_dates ON academic_calendar_events(start_date, end_date);
"""

MIGRATIONS: list[str] = [_V1, _V2, _V3]  # index + 1 == schema version
SCHEMA_VERSION = len(MIGRATIONS)

# link tables: name -> (owner column, target column)
LINK_TABLE_CONFIG: dict[str, tuple[str, str]] = {
    "task_topic_links": ("task_id", "topic_id"),
    "exam_topic_links": ("exam_id", "topic_id"),
    "task_subtopic_links": ("task_id", "subtopic_id"),
    "exam_subtopic_links": ("exam_id", "subtopic_id"),
    "learning_event_outcomes": ("event_id", "outcome_id"),
}
# Backward compatibility
LINK_TABLES: dict[str, str] = {k: v[0] for k, v in LINK_TABLE_CONFIG.items()}


class Database:
    """Thin repository around one sqlite3 connection."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        # isolation_level=None -> autocommit; transactions are managed explicitly.
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._depth = 0
        self._columns: dict[str, tuple[str, ...]] = {}
        self.migrate()

    # ------------------------------------------------------------------ infra
    def close(self) -> None:
        self._conn.close()

    def foreign_keys_enabled(self) -> bool:
        return bool(self._conn.execute("PRAGMA foreign_keys").fetchone()[0])

    def schema_version(self) -> int:
        return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> None:
        current = self.schema_version()
        for target, script in enumerate(MIGRATIONS, start=1):
            if target <= current:
                continue
            try:
                self._conn.executescript(
                    f"BEGIN;\n{script}\nPRAGMA user_version = {target};\nCOMMIT;"
                )
            except sqlite3.Error:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise
        self._columns.clear()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Nestable transaction: outermost = BEGIN/COMMIT, inner = SAVEPOINT."""
        depth = self._depth
        if depth == 0:
            self._conn.execute("BEGIN")
        else:
            self._conn.execute(f"SAVEPOINT sp{depth}")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if depth == 0:
                self._conn.execute("ROLLBACK")
            else:
                self._conn.execute(f"ROLLBACK TO sp{depth}")
                self._conn.execute(f"RELEASE sp{depth}")
            raise
        else:
            self._depth -= 1
            if depth == 0:
                self._conn.execute("COMMIT")
            else:
                self._conn.execute(f"RELEASE sp{depth}")

    # ------------------------------------------------------ schema validation
    def table_columns(self, table: str) -> tuple[str, ...]:
        if table not in self._columns:
            rows = self._conn.execute(f"PRAGMA table_info({_ident(table)})").fetchall()
            if not rows:
                raise ValueError(f"Unknown table: {table!r}")
            self._columns[table] = tuple(r["name"] for r in rows)
        return self._columns[table]

    def _check_columns(self, table: str, names: Sequence[str]) -> None:
        valid = self.table_columns(table)
        for n in names:
            if n not in valid:
                raise ValueError(f"Unknown column {n!r} for table {table!r}")

    def _order_clause(self, table: str, order_by: Sequence[str]) -> str:
        parts: list[str] = []
        for item in order_by:
            col, _, direction = item.partition(" ")
            self._check_columns(table, [col])
            if direction.upper() not in ("", "ASC", "DESC"):
                raise ValueError(f"Invalid order direction: {direction!r}")
            parts.append(f"{col} {direction.upper()}".strip())
        return f" ORDER BY {', '.join(parts)}" if parts else ""

    def _where_clause(self, table: str, where: Mapping[str, Any] | None) -> tuple[str, list[Any]]:
        if not where:
            return "", []
        self._check_columns(table, list(where))
        clauses: list[str] = []
        params: list[Any] = []
        for col, val in where.items():
            if val is None:
                clauses.append(f"{col} IS NULL")
            else:
                clauses.append(f"{col} = ?")
                params.append(val)
        return " WHERE " + " AND ".join(clauses), params

    # --------------------------------------------------------- generic CRUD
    def insert(self, table: str, values: Mapping[str, Any]) -> int:
        cols = list(values)
        self._check_columns(table, cols)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        return int(self._conn.execute(sql, [values[c] for c in cols]).lastrowid)

    def update(self, table: str, key_value: Any, values: Mapping[str, Any], key: str = "id") -> None:
        cols = list(values)
        if not cols:
            return
        self._check_columns(table, [key, *cols])
        sets = ", ".join(f"{c} = ?" for c in cols)
        self._conn.execute(f"UPDATE {table} SET {sets} WHERE {key} = ?", [*(values[c] for c in cols), key_value])

    def upsert(self, table: str, values: Mapping[str, Any], conflict: str) -> None:
        cols = list(values)
        self._check_columns(table, [conflict, *cols])
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != conflict)
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, [values[c] for c in cols])

    def delete(self, table: str, where: Mapping[str, Any]) -> int:
        if not where:
            raise ValueError("delete() requires a where clause")
        clause, params = self._where_clause(table, where)
        return self._conn.execute(f"DELETE FROM {table}{clause}", params).rowcount

    def get(self, table: str, key_value: Any, key: str = "id") -> dict[str, Any] | None:
        self._check_columns(table, [key])
        row = self._conn.execute(f"SELECT * FROM {table} WHERE {key} = ?", [key_value]).fetchone()
        return dict(row) if row else None

    def select(self, table: str, where: Mapping[str, Any] | None = None,
               order_by: Sequence[str] = ()) -> list[dict[str, Any]]:
        self.table_columns(table)
        clause, params = self._where_clause(table, where)
        sql = f"SELECT * FROM {table}{clause}{self._order_clause(table, order_by)}"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def select_range(self, table: str, column: str, start: str, end: str,
                     where: Mapping[str, Any] | None = None,
                     order_by: Sequence[str] = ()) -> list[dict[str, Any]]:
        """Rows with ``start <= column <= end`` (ISO strings sort correctly)."""
        self._check_columns(table, [column])
        clause, params = self._where_clause(table, where)
        joiner = " AND " if clause else " WHERE "
        sql = (f"SELECT * FROM {table}{clause}{joiner}{column} >= ? AND {column} <= ?"
               f"{self._order_clause(table, order_by)}")
        return [dict(r) for r in self._conn.execute(sql, [*params, start, end]).fetchall()]

    # ------------------------------------------------------ curriculum queries
    def units_for_subject(self, subject_id: int) -> list[dict[str, Any]]:
        sql = """SELECT * FROM units
                 WHERE subject_id = ?
                 ORDER BY order_no, COALESCE(start_date, ''), id"""
        return [dict(r) for r in self._conn.execute(sql, [subject_id]).fetchall()]

    def topics_for_subject(self, subject_id: int, unit_id: int | None = None) -> list[dict[str, Any]]:
        where: dict[str, Any] = {"subject_id": subject_id}
        if unit_id is not None:
            where["unit_id"] = unit_id
        return self.select("topics", where, order_by=["name"])

    def subtopics_for_topic(self, topic_id: int) -> list[dict[str, Any]]:
        sql = """SELECT * FROM subtopics
                 WHERE topic_id = ?
                 ORDER BY order_no, id"""
        return [dict(r) for r in self._conn.execute(sql, [topic_id]).fetchall()]

    def subtopics_for_unit(self, unit_id: int) -> list[dict[str, Any]]:
        sql = """SELECT st.*, t.name AS topic_name, t.unit_id
                 FROM subtopics st
                 JOIN topics t ON t.id = st.topic_id
                 WHERE t.unit_id = ?
                 ORDER BY t.name, st.order_no, st.id"""
        return [dict(r) for r in self._conn.execute(sql, [unit_id]).fetchall()]

    def outcomes_for_subtopic(self, subtopic_id: int) -> list[dict[str, Any]]:
        sql = """SELECT * FROM learning_outcomes
                 WHERE subtopic_id = ?
                 ORDER BY order_no, id"""
        return [dict(r) for r in self._conn.execute(sql, [subtopic_id]).fetchall()]

    def learning_events_for_subject(self, subject_id: int) -> list[dict[str, Any]]:
        sql = """SELECT e.*, t.name AS topic_name, t.subject_id AS subject_id,
                        t.unit_id AS unit_id, u.name AS unit_name,
                        st.id AS subtopic_id, st.name AS subtopic_name
                 FROM learning_events e
                 JOIN topics t ON t.id = e.topic_id
                 LEFT JOIN units u ON u.id = t.unit_id
                 LEFT JOIN subtopics st ON st.id = e.subtopic_id
                 WHERE t.subject_id = ?
                 ORDER BY e.event_date, COALESCE(e.period_start, 0), e.id"""
        return [dict(r) for r in self._conn.execute(sql, [subject_id]).fetchall()]

    def memory_states_for_subject(self, subject_id: int) -> list[dict[str, Any]]:
        sql = """SELECT m.*, t.name AS topic_name, t.unit_id AS unit_id, u.name AS unit_name
                 FROM memory_states m
                 JOIN topics t ON t.id = m.topic_id
                 LEFT JOIN units u ON u.id = t.unit_id
                 WHERE t.subject_id = ?
                 ORDER BY m.next_review_date, t.name"""
        return [dict(r) for r in self._conn.execute(sql, [subject_id]).fetchall()]

    def subtopic_memory_states_for_subject(self, subject_id: int) -> list[dict[str, Any]]:
        sql = """SELECT sms.*, st.name AS subtopic_name, st.topic_id, t.name AS topic_name,
                        t.unit_id, u.name AS unit_name
                 FROM subtopic_memory_states sms
                 JOIN subtopics st ON st.id = sms.subtopic_id
                 JOIN topics t ON t.id = st.topic_id
                 LEFT JOIN units u ON u.id = t.unit_id
                 WHERE t.subject_id = ?
                 ORDER BY sms.next_review_date, st.order_no"""
        return [dict(r) for r in self._conn.execute(sql, [subject_id]).fetchall()]

    # --------------------------------------------------------- link management
    def set_links(self, link_table: str, owner_id: int, target_ids: Sequence[int]) -> None:
        if link_table not in LINK_TABLE_CONFIG:
            raise ValueError(f"Unknown link table: {link_table}")
        owner_col, target_col = LINK_TABLE_CONFIG[link_table]
        with self.transaction():
            self._conn.execute(f"DELETE FROM {link_table} WHERE {owner_col} = ?", [owner_id])
            for tid in dict.fromkeys(target_ids):
                self._conn.execute(
                    f"INSERT INTO {link_table} ({owner_col}, {target_col}) VALUES (?, ?)", [owner_id, tid])

    def set_topic_links(self, link_table: str, owner_id: int, topic_ids: Sequence[int]) -> None:
        self.set_links(link_table, owner_id, topic_ids)

    def topic_link_map(self, link_table: str) -> dict[int, list[int]]:
        if link_table not in LINK_TABLE_CONFIG:
            raise ValueError(f"Unknown link table: {link_table}")
        owner_col, target_col = LINK_TABLE_CONFIG[link_table]
        rows = self._conn.execute(
            f"SELECT {owner_col} AS owner, {target_col} AS target FROM {link_table} ORDER BY {owner_col}, {target_col}").fetchall()
        result: dict[int, list[int]] = {}
        for r in rows:
            result.setdefault(int(r["owner"]), []).append(int(r["target"]))
        return result

    def find_review_tasks(self, topic_id: int, source: str, status: str = "PENDING") -> list[dict[str, Any]]:
        sql = """SELECT t.* FROM tasks t JOIN task_topic_links l ON l.task_id = t.id
                 WHERE l.topic_id = ? AND t.task_class = 'REVIEW'
                   AND t.review_source = ? AND t.status = ?
                 ORDER BY t.id"""
        return [dict(r) for r in self._conn.execute(sql, [topic_id, source, status]).fetchall()]

    def delete_review_tasks_for_topics(self, topic_ids: Sequence[int]) -> None:
        if not topic_ids:
            return
        marks = ", ".join("?" * len(topic_ids))
        self._conn.execute(
            f"""DELETE FROM tasks WHERE task_class = 'REVIEW' AND id IN
                (SELECT task_id FROM task_topic_links WHERE topic_id IN ({marks}))""", list(topic_ids))

    def mark_stale_sessions_missed(self, today_iso: str, now_hhmm: str) -> int:
        """PLANNED sessions that started before 'now' and were never completed -> MISSED."""
        sql = """UPDATE study_sessions SET status = 'MISSED'
                 WHERE status = 'PLANNED'
                   AND (session_date < ? OR (session_date = ? AND start_time < ?))"""
        return self._conn.execute(sql, [today_iso, today_iso, now_hhmm]).rowcount

    def delete_planned_sessions(self) -> int:
        return self.delete("study_sessions", {"status": "PLANNED"})

    # ------------------------------------------------------- academic calendar
    def academic_terms(self, student_id: int = 1) -> list[dict[str, Any]]:
        sql = """SELECT * FROM academic_terms
                 WHERE student_id = ?
                 ORDER BY start_date, term_no"""
        return [dict(r) for r in self._conn.execute(sql, [student_id]).fetchall()]

    def academic_calendar_events_for_range(self, start_date: str, end_date: str, student_id: int = 1) -> list[dict[str, Any]]:
        sql = """SELECT * FROM academic_calendar_events
                 WHERE student_id = ?
                   AND start_date <= ? AND end_date >= ?
                 ORDER BY start_date, id"""
        return [dict(r) for r in self._conn.execute(sql, [student_id, end_date, start_date]).fetchall()]

    def school_status_for_date(self, target_date: str, student_id: int = 1) -> dict[str, Any] | None:
        """Belirtilen gün için resmi okul durumunu (OPEN, CLOSED, HALF_DAY) döner."""
        sql = """SELECT * FROM academic_calendar_events
                 WHERE student_id = ?
                   AND start_date <= ? AND end_date >= ?
                 ORDER BY CASE day_status WHEN 'CLOSED' THEN 1 WHEN 'HALF_DAY' THEN 2 ELSE 3 END, id
                 LIMIT 1"""
        row = self._conn.execute(sql, [student_id, target_date, target_date]).fetchone()
        return dict(row) if row else None

    def seed_default_academic_calendar(self, student_id: int = 1) -> None:
        """2026-2027 MEB ve Diyanet resmi takvimini veritabanına ekler."""
        have = self.select("academic_calendar_events", {"student_id": student_id})
        if have:
            return  # Zaten tohumlanmış

        with self.transaction():
            # 1. Dönemler (2 Dönem, 4 Çeyrek / Periyot)
            terms = [
                ("1. Dönem", "SEMESTER", 1, "2026-09-14", "2027-01-22"),
                ("1. Dönem 1. Çeyrek", "QUARTER", 1, "2026-09-14", "2026-11-13"),
                ("1. Dönem 2. Çeyrek", "QUARTER", 2, "2026-11-23", "2027-01-22"),
                ("2. Dönem", "SEMESTER", 2, "2027-02-08", "2027-06-25"),
                ("2. Dönem 3. Çeyrek", "QUARTER", 3, "2027-02-08", "2027-03-05"),
                ("2. Dönem 4. Çeyrek", "QUARTER", 4, "2027-03-15", "2027-06-25"),
            ]
            for name, t_type, t_no, s_date, e_date in terms:
                self.insert("academic_terms", {
                    "student_id": student_id,
                    "name": name,
                    "term_type": t_type,
                    "term_no": t_no,
                    "start_date": s_date,
                    "end_date": e_date,
                    "created_at": "2026-09-01T00:00:00"
                })

            # 2. 2026-2027 Resmi Okul Var/Yok ve Tatil Takvimi
            events = [
                ("Okul Açılışı", "2026-09-14", "2026-09-14", "OPEN", "SEMESTER_START", "2026-2027 Eğitim Öğretim Yılı Başlangıcı"),
                ("Cumhuriyet Bayramı Arifesi", "2026-10-28", "2026-10-28", "HALF_DAY", "HOLIDAY", "28 Ekim Öğleden Sonra Tatil"),
                ("Test", "2026-10-16", "2026-10-16", "CLOSED", "HOLIDAY", "test tatili"),
                ("Cumhuriyet Bayramı", "2026-10-29", "2026-10-29", "CLOSED", "HOLIDAY", "29 Ekim Cumhuriyet Bayramı"),
                ("1. Ara Tatil", "2026-11-16", "2026-11-20", "CLOSED", "BREAK", "1. Dönem Ara Tatili"),
                ("Yılbaşı Tatili", "2027-01-01", "2027-01-01", "CLOSED", "HOLIDAY", "Yılbaşı Resmi Tatili"),
                ("1. Dönem Karne Günü", "2027-01-22", "2027-01-22", "OPEN", "SEMESTER_END", "1. Yarıyıl Sonu"),
                ("Yarıyıl (Sömestr) Tatili", "2027-01-25", "2027-02-05", "CLOSED", "BREAK", "15 Tatil"),
                ("2. Dönem Okul Açılışı", "2027-02-08", "2027-02-08", "OPEN", "SEMESTER_START", "2. Yarıyıl Başlangıcı"),
                ("Ramazan Bayramı Arifesi", "2027-03-08", "2027-03-08", "HALF_DAY", "HOLIDAY", "Arefe Günü Öğleden Sonra Tatil"),
                ("Ramazan Bayramı", "2027-03-09", "2027-03-11", "CLOSED", "HOLIDAY", "Ramazan Bayramı"),
                ("2. Ara Tatil", "2027-03-12", "2027-03-12", "CLOSED", "BREAK", "2. Dönem Ara Tatili Devamı"),
                ("23 Nisan Ulusal Egemenlik ve Çocuk Bayramı", "2027-04-23", "2027-04-23", "CLOSED", "HOLIDAY", "23 Nisan Resmi Tatili"),
                ("1 Mayıs Emek ve Dayanışma Günü", "2027-05-01", "2027-05-01", "CLOSED", "HOLIDAY", "Hafta sonuna denk gelen resmi tatil"),
                ("Kurban Bayramı Arifesi", "2027-05-15", "2027-05-15", "HALF_DAY", "HOLIDAY", "Hafta sonu arife"),
                ("Kurban Bayramı ve 19 Mayıs", "2027-05-17", "2027-05-19", "CLOSED", "HOLIDAY", "Kurban Bayramı ve 19 Mayıs Atatürk'ü Anma Gençlik ve Spor Bayramı"),
                ("Karne Günü / Okul Kapanışı", "2027-06-25", "2027-06-25", "OPEN", "SEMESTER_END", "2026-2027 Eğitim Öğretim Yılı Kapanışı"),
            ]
            for title, s_date, e_date, status, ev_type, desc in events:
                self.insert("academic_calendar_events", {
                    "student_id": student_id,
                    "title": title,
                    "start_date": s_date,
                    "end_date": e_date,
                    "day_status": status,
                    "event_type": ev_type,
                    "description": desc,
                    "created_at": "2026-09-01T00:00:00"
                })

    # -------------------------------------------------------------- settings
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", [key]).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.upsert("settings", {"key": key, "value": value}, conflict="key")


def _ident(name: str) -> str:
    """Validate a bare SQL identifier (used for PRAGMA, which cannot be parameterized)."""
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Invalid identifier: {name!r}")
    return name