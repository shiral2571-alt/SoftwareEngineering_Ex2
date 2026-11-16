"""SQLite storage. One schema for the whole app (KISS). See docs/SRS.md §3 for the domain model."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,               -- stable key derived from the name (no ID numbers, SRS D-3)
    name       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollments (
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    student_id TEXT NOT NULL REFERENCES students(student_id),
    PRIMARY KEY (course_id, student_id)
);
CREATE TABLE IF NOT EXISTS devices (
    device_token TEXT PRIMARY KEY,
    student_id   TEXT NOT NULL UNIQUE REFERENCES students(student_id),  -- one name <-> one phone
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS lectures (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    title      TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'draft',  -- draft | open | closed
    created_at REAL NOT NULL,
    opened_at  REAL,
    closed_at  REAL
);
CREATE TABLE IF NOT EXISTS checkin_windows (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    channel    TEXT NOT NULL,                  -- sound | qr
    opened_at  REAL NOT NULL,
    closed_at  REAL                            -- NULL while open; only the lecturer closes it (D-14)
);
CREATE TABLE IF NOT EXISTS tokens (
    token      TEXT PRIMARY KEY,
    window_id  INTEGER NOT NULL REFERENCES checkin_windows(id),
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance (
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    student_id TEXT NOT NULL REFERENCES students(student_id),
    status     TEXT NOT NULL,                  -- present | late | absent
    method     TEXT NOT NULL,                  -- sound | qr | manual
    at         REAL NOT NULL,
    PRIMARY KEY (lecture_id, student_id)
);
CREATE TABLE IF NOT EXISTS polls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id   INTEGER NOT NULL REFERENCES lectures(id),
    title        TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'draft', -- draft | live | closed
    show_correct INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id  INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text     TEXT NOT NULL,
    kind     TEXT NOT NULL,                    -- quiz | choice | text
    options  TEXT NOT NULL DEFAULT '[]',       -- JSON list of strings
    correct  INTEGER                           -- option index, quiz only
);
CREATE TABLE IF NOT EXISTS answers (
    question_id  INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    student_id   TEXT NOT NULL REFERENCES students(student_id),
    option_index INTEGER,
    text         TEXT,
    at           REAL NOT NULL,
    PRIMARY KEY (question_id, student_id)
);
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    student_id TEXT REFERENCES students(student_id),  -- NULL = fully anonymous (D-8)
    text       TEXT NOT NULL,
    at         REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS replies (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    text    TEXT NOT NULL,
    at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS upvotes (
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    student_id TEXT NOT NULL REFERENCES students(student_id),
    PRIMARY KEY (post_id, student_id)
);
CREATE TABLE IF NOT EXISTS materials (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    kind       TEXT NOT NULL,                  -- file | report
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,                  -- text content (reports, transcripts, notes)
    visible_to_students INTEGER NOT NULL DEFAULT 0,
    at         REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open the database (":memory:" works for tests) and make sure the schema exists."""
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
