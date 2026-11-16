"""Attendance: check-in windows, short-lived tokens (sound / rotating QR) and statuses (SRS FR-4.x).

Flow: the lecturer opens a check-in window → the laptop issues a fresh token every few seconds
(played as sound, or shown as a QR) → phones report what they heard/scanned → the server decides.
The window stays open until the lecturer ends it (D-14). Whoever missed it is Absent; the lecturer
can set Late or Present by hand (D-6).
"""
import secrets
import sqlite3
import time
from dataclasses import dataclass

# Look-alike characters (O/0, I/1/L, S/5, B/8, Z/2) removed so a misread is less likely.
TOKEN_ALPHABET = "ACDEFGHJKMNPQRTUVWXY34679"
TOKEN_LENGTH = 6
TOKEN_TTL = {"sound": 20.0, "qr": 30.0}  # seconds; a recording or photo sent to a friend is soon useless

PRESENT, LATE, ABSENT = "present", "late", "absent"
STATUSES = (PRESENT, LATE, ABSENT)


@dataclass
class HeardResult:
    ok: bool
    message: str


class AttendanceService:
    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    # ----- check-in windows -----
    def open_window(self, lecture_id: int, channel: str) -> int:
        """Start a check-in window. Only one window is open at a time; opening a new one ends the old one."""
        if channel not in TOKEN_TTL:
            raise ValueError("channel must be 'sound' or 'qr'")
        lec = self.db.execute("SELECT state FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
        if lec is None or lec["state"] != "open":
            raise ValueError("Open the lecture first")
        self.close_window(lecture_id)
        return self.db.execute("INSERT INTO checkin_windows(lecture_id, channel, opened_at) VALUES (?, ?, ?)",
                               (lecture_id, channel, self.clock())).lastrowid

    def close_window(self, lecture_id: int) -> None:
        self.db.execute("UPDATE checkin_windows SET closed_at = ? WHERE lecture_id = ? AND closed_at IS NULL",
                        (self.clock(), lecture_id))

    def open_window_of(self, lecture_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM checkin_windows WHERE lecture_id = ? AND closed_at IS NULL",
                            (lecture_id,)).fetchone()
        return dict(r) if r else None

    # ----- tokens -----
    def issue_token(self, lecture_id: int) -> str:
        """A fresh one-time token for the open window (the laptop asks every ~10 s for sound, ~15 s for QR)."""
        window = self.open_window_of(lecture_id)
        if window is None:
            raise ValueError("No check-in window is open")
        token = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))
        self.db.execute("INSERT INTO tokens(token, window_id, expires_at) VALUES (?, ?, ?)",
                        (token, window["id"], self.clock() + TOKEN_TTL[window["channel"]]))
        return token

    def heard(self, student_id: str, token: str) -> HeardResult:
        """A phone reports a token it heard (or scanned). The server is the judge."""
        token = (token or "").strip().upper()
        row = self.db.execute(
            "SELECT t.expires_at, w.lecture_id, w.channel, w.closed_at, e.student_id AS enrolled "
            "FROM tokens t JOIN checkin_windows w ON w.id = t.window_id "
            "JOIN lectures l ON l.id = w.lecture_id "
            "LEFT JOIN enrollments e ON e.course_id = l.course_id AND e.student_id = ? "
            "WHERE t.token = ?", (student_id, token)).fetchone()
        if row is None:
            return HeardResult(False, "Unknown code")
        if row["closed_at"] is not None:
            return HeardResult(False, "Check-in has ended — ask the lecturer")
        if row["expires_at"] < self.clock():
            return HeardResult(False, "Code expired — scan or listen again")
        if row["enrolled"] is None:
            return HeardResult(False, "You are not on this course's list")
        if self.status_of(row["lecture_id"], student_id) == PRESENT:
            return HeardResult(True, "Already checked in")
        self._set(row["lecture_id"], student_id, PRESENT, row["channel"])
        return HeardResult(True, "Checked in")

    # ----- statuses -----
    def set_status(self, lecture_id: int, student_id: str, status: str) -> None:
        """Lecturer override — also after the lecture is closed (FR-4.8)."""
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        self._set(lecture_id, student_id, status, "manual")

    def _set(self, lecture_id: int, student_id: str, status: str, method: str) -> None:
        self.db.execute(
            "INSERT INTO attendance(lecture_id, student_id, status, method, at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(lecture_id, student_id) DO UPDATE SET status = excluded.status, "
            "method = excluded.method, at = excluded.at", (lecture_id, student_id, status, method, self.clock()))

    def status_of(self, lecture_id: int, student_id: str) -> str:
        r = self.db.execute("SELECT status FROM attendance WHERE lecture_id = ? AND student_id = ?",
                            (lecture_id, student_id)).fetchone()
        return r["status"] if r else ABSENT  # no record = Absent

    def record_of(self, lecture_id: int, student_id: str) -> dict:
        r = self.db.execute("SELECT status, method, at FROM attendance WHERE lecture_id = ? AND student_id = ?",
                            (lecture_id, student_id)).fetchone()
        return dict(r) if r else {"status": ABSENT, "method": "", "at": None}

    def sheet(self, lecture_id: int, students) -> list[dict]:
        """The live spreadsheet: one row per enrolled student."""
        return [{"student_id": s.student_id, "name": s.name, **self.record_of(lecture_id, s.student_id)}
                for s in students]
