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

MIGRATIONS: list[str] = [_V1, _V2]  # index + 1 == schema version
SCHEMA_VERSION = len(MIGRATIONS)

# link tables: name -> owner column
LINK_TABLES: dict[str, str] = {"task_topic_links": "task_id", "exam_topic_links": "exam_id"}


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
        self.table_columns(table)                      # validates the table name
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

    # ------------------------------------------------------ specific queries
    def units_for_subject(self, subject_id: int) -> list[dict[str, Any]]:
        sql = """SELECT * FROM units
                 WHERE subject_id = ?
                 ORDER BY order_no, COALESCE(start_date, ''), id"""
        return [dict(r) for r in self._conn.execute(sql, [subject_id]).fetchall()]

    def learning_events_for_subject(self, subject_id: int) -> list[dict[str, Any]]:
        sql = """SELECT e.*, t.name AS topic_name, t.subject_id AS subject_id,
                        t.unit_id AS unit_id, u.name AS unit_name
                 FROM learning_events e
                 JOIN topics t ON t.id = e.topic_id
                 LEFT JOIN units u ON u.id = t.unit_id
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

    def set_topic_links(self, link_table: str, owner_id: int, topic_ids: Sequence[int]) -> None:
        owner_col = LINK_TABLES[link_table]
        with self.transaction():
            self._conn.execute(f"DELETE FROM {link_table} WHERE {owner_col} = ?", [owner_id])
            for tid in dict.fromkeys(topic_ids):  # de-duplicate, keep order
                self._conn.execute(
                    f"INSERT INTO {link_table} ({owner_col}, topic_id) VALUES (?, ?)", [owner_id, tid])

    def topic_link_map(self, link_table: str) -> dict[int, list[int]]:
        owner_col = LINK_TABLES[link_table]
        rows = self._conn.execute(
            f"SELECT {owner_col} AS owner, topic_id FROM {link_table} ORDER BY {owner_col}, topic_id").fetchall()
        result: dict[int, list[int]] = {}
        for r in rows:
            result.setdefault(int(r["owner"]), []).append(int(r["topic_id"]))
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