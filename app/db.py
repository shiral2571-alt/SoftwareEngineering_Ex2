"""SQLite storage. One small schema for the whole demo (KISS)."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    device_token TEXT PRIMARY KEY,
    student_id   TEXT NOT NULL REFERENCES students(student_id),
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS lectures (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at   REAL
);
CREATE TABLE IF NOT EXISTS pulses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    started_at REAL NOT NULL,
    ends_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    token      TEXT PRIMARY KEY,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    pulse_id   INTEGER REFERENCES pulses(id),   -- NULL = check-in token
    channel    TEXT NOT NULL,                   -- 'sound' | 'qr'
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins (
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    student_id TEXT NOT NULL REFERENCES students(student_id),
    at         REAL NOT NULL,
    method     TEXT NOT NULL,                   -- 'sound' | 'qr' | 'manual'
    device_token TEXT,
    PRIMARY KEY (lecture_id, student_id)
);
CREATE TABLE IF NOT EXISTS pulse_hits (
    pulse_id   INTEGER NOT NULL REFERENCES pulses(id),
    student_id TEXT NOT NULL REFERENCES students(student_id),
    at         REAL NOT NULL,
    PRIMARY KEY (pulse_id, student_id)
);
CREATE TABLE IF NOT EXISTS polls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    question   TEXT NOT NULL,
    options    TEXT NOT NULL,                   -- JSON list of strings
    is_open    INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS votes (
    poll_id    INTEGER NOT NULL REFERENCES polls(id),
    student_id TEXT NOT NULL REFERENCES students(student_id),
    option_index INTEGER NOT NULL,
    PRIMARY KEY (poll_id, student_id)
);
CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    student_id TEXT REFERENCES students(student_id),
    anonymous  INTEGER NOT NULL DEFAULT 0,
    text       TEXT NOT NULL,
    at         REAL NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open the database (":memory:" works for tests) and make sure the schema exists."""
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
