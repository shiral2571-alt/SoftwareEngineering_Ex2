"""Device binding: the sound token proves *presence*, this proves *who*.

After a student verifies once (name + last 4 ID digits), the server issues a random device token,
kept in an HttpOnly cookie. The phone never has to type anything again.
"""
import secrets
import sqlite3
import time

from .roster import CourseRoster, Student


class DeviceRegistry:
    def __init__(self, db: sqlite3.Connection, roster: CourseRoster, clock=time.time):
        self.db, self.roster, self.clock = db, roster, clock

    def bind(self, student: Student) -> str:
        """Issue a new device token for this student. Earlier devices stay valid but get flagged."""
        token = secrets.token_urlsafe(24)
        self.db.execute(
            "INSERT INTO devices(device_token, student_id, created_at) VALUES (?, ?, ?)",
            (token, student.student_id, self.clock()),
        )
        return token

    def student_for(self, device_token: str | None) -> Student | None:
        if not device_token:
            return None
        r = self.db.execute("SELECT student_id FROM devices WHERE device_token = ?", (device_token,)).fetchone()
        return self.roster.get(r["student_id"]) if r else None

    def device_count(self, student_id: str) -> int:
        """More than one device for a student is shown to the lecturer as a flag (possible sharing)."""
        return self.db.execute("SELECT COUNT(*) FROM devices WHERE student_id = ?", (student_id,)).fetchone()[0]

    def reset(self, student_id: str) -> None:
        """Lecturer action: forget all devices of a student (lost phone etc.)."""
        self.db.execute("DELETE FROM devices WHERE student_id = ?", (student_id,))
