"""Device binding: the sound token proves *presence*, this proves *who*.

The course list has names only (no ID numbers), so identity works like a seat label:
the first phone that picks a name owns it. The server issues a random device token, kept in an HttpOnly
cookie, so the phone never has to choose again. If someone else already took your name, the lecturer
sees it immediately (you complain) and resets it with one click.
"""
import secrets
import sqlite3
import time
from dataclasses import dataclass

from .roster import CourseRoster, Student


@dataclass
class ClaimResult:
    ok: bool
    device_token: str = ""
    error: str = ""


class DeviceRegistry:
    def __init__(self, db: sqlite3.Connection, roster: CourseRoster, clock=time.time):
        self.db, self.roster, self.clock = db, roster, clock

    def claim(self, student: Student, current_device: str | None = None) -> ClaimResult:
        """Bind `student` to this phone. One name ↔ one phone.

        - The name is free → issue a new device token.
        - This phone already owns the name → keep its token (re-opening the page is harmless).
        - Another phone owns the name → refuse; only the lecturer can reset it.
        A phone that switches to a different name releases its old name, so nobody stays locked out.
        """
        owner = self.db.execute("SELECT device_token FROM devices WHERE student_id = ?",
                                (student.student_id,)).fetchone()
        if owner is not None:
            if owner["device_token"] == current_device:
                return ClaimResult(True, current_device)
            return ClaimResult(False, error=f"“{student.name}” is already registered on another phone. "
                                            "Ask the lecturer to reset it.")
        if current_device:
            self.db.execute("DELETE FROM devices WHERE device_token = ?", (current_device,))
        token = secrets.token_urlsafe(24)
        self.db.execute("INSERT INTO devices(device_token, student_id, created_at) VALUES (?, ?, ?)",
                        (token, student.student_id, self.clock()))
        return ClaimResult(True, token)

    def student_for(self, device_token: str | None) -> Student | None:
        if not device_token:
            return None
        r = self.db.execute("SELECT student_id FROM devices WHERE device_token = ?", (device_token,)).fetchone()
        return self.roster.get(r["student_id"]) if r else None

    def is_registered(self, student_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM devices WHERE student_id = ?", (student_id,)).fetchone() is not None

    def reset(self, student_id: str) -> None:
        """Lecturer action: free the name (wrong person took it, lost phone, new phone)."""
        self.db.execute("DELETE FROM devices WHERE student_id = ?", (student_id,))
