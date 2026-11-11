"""Attendance: lectures, short-lived tokens (sound / rotating QR), check-ins and presence pulses."""
import secrets
import sqlite3
import time
from dataclasses import dataclass

# Look-alike characters (O/0, I/1/L, S/5, B/8, Z/2) removed so a misread is less likely.
TOKEN_ALPHABET = "ACDEFGHJKMNPQRTUVWXY34679"
TOKEN_LENGTH = 6
SOUND_TOKEN_TTL = 20.0   # seconds; a recording sent to a friend is useless after this
QR_TOKEN_TTL = 30.0      # QR rotates every ~15 s on the projector, accepted a bit longer
PULSE_WINDOW = 60.0      # a presence pulse stays open for one minute


def attendance_status(checked_in: bool, pulses_heard: int, pulses_total: int) -> str:
    """Final status shown in the lecturer's spreadsheet.

    Returns one of: "Present", "Partial", "Absent".

    TODO(you + partner): this is the attendance *policy* (docs/CONCEPT.md §10, "threshold for present").
    Decide how pulses count. Questions to settle:
      - Is a student who checked in but heard 0 of 3 pulses "Partial" or "Absent"?
      - Does someone who missed check-in (came late) but heard most pulses count as "Present"?
      - What ratio is enough — 2 of 3? at least half? Should 1 missed pulse be forgiven
        (a phone may simply have missed one broadcast)?
    The placeholder below ignores pulses on purpose, so the demo works until you decide.
    """
    if pulses_total == 0:
        return "Present" if checked_in else "Absent"
    return "Present" if checked_in else "Absent"  # placeholder — replace with your rule


@dataclass
class HeardResult:
    ok: bool
    message: str
    kind: str = ""  # 'checkin' | 'pulse'


class AttendanceService:
    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    # ----- lectures -----
    def start_lecture(self, title: str) -> int:
        self.end_lecture()
        cur = self.db.execute("INSERT INTO lectures(title, started_at) VALUES (?, ?)",
                              (title.strip() or "Lecture", self.clock()))
        return cur.lastrowid

    def end_lecture(self) -> None:
        self.db.execute("UPDATE lectures SET ended_at = ? WHERE ended_at IS NULL", (self.clock(),))

    def current_lecture(self) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM lectures WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()

    def lectures(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM lectures ORDER BY id").fetchall()

    # ----- pulses -----
    def start_pulse(self, lecture_id: int) -> int:
        now = self.clock()
        cur = self.db.execute("INSERT INTO pulses(lecture_id, started_at, ends_at) VALUES (?, ?, ?)",
                              (lecture_id, now, now + PULSE_WINDOW))
        return cur.lastrowid

    def active_pulse(self, lecture_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM pulses WHERE lecture_id = ? AND ends_at > ? ORDER BY id DESC LIMIT 1",
                               (lecture_id, self.clock())).fetchone()

    def pulse_count(self, lecture_id: int) -> int:
        return self.db.execute("SELECT COUNT(*) FROM pulses WHERE lecture_id = ?", (lecture_id,)).fetchone()[0]

    # ----- tokens -----
    def issue_token(self, lecture_id: int, channel: str = "sound") -> str:
        """New one-time token for the current moment. During a pulse window it counts for the pulse."""
        pulse = self.active_pulse(lecture_id)
        ttl = QR_TOKEN_TTL if channel == "qr" else SOUND_TOKEN_TTL
        token = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))
        self.db.execute("INSERT INTO tokens(token, lecture_id, pulse_id, channel, expires_at) VALUES (?, ?, ?, ?, ?)",
                        (token, lecture_id, pulse["id"] if pulse else None, channel, self.clock() + ttl))
        return token

    def heard(self, student_id: str, token: str, device_token: str | None = None) -> HeardResult:
        """A phone reports a token it heard (or scanned). The server decides if it counts."""
        token = (token or "").strip().upper()
        row = self.db.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
        if row is None:
            return HeardResult(False, "Unknown code")
        if row["expires_at"] < self.clock():
            return HeardResult(False, "Code expired")
        lecture = self.current_lecture()
        if lecture is None or lecture["id"] != row["lecture_id"]:
            return HeardResult(False, "This code is not for the current lecture")

        method = row["channel"]
        newly_checked_in = self._check_in(row["lecture_id"], student_id, method, device_token)
        if row["pulse_id"] is not None:
            self.db.execute("INSERT OR IGNORE INTO pulse_hits(pulse_id, student_id, at) VALUES (?, ?, ?)",
                            (row["pulse_id"], student_id, self.clock()))
            return HeardResult(True, "Presence confirmed", "pulse")
        return HeardResult(True, "Checked in" if newly_checked_in else "Already checked in", "checkin")

    def manual_check_in(self, lecture_id: int, student_id: str) -> None:
        """Lecturer override (e.g. a phone without a microphone). Shown as 'manual' in the sheet."""
        self._check_in(lecture_id, student_id, "manual", None)

    def _check_in(self, lecture_id: int, student_id: str, method: str, device_token: str | None) -> bool:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO checkins(lecture_id, student_id, at, method, device_token) VALUES (?, ?, ?, ?, ?)",
            (lecture_id, student_id, self.clock(), method, device_token))
        return cur.rowcount == 1

    # ----- reports -----
    def student_summary(self, lecture_id: int, student_id: str) -> dict:
        c = self.db.execute("SELECT * FROM checkins WHERE lecture_id = ? AND student_id = ?",
                            (lecture_id, student_id)).fetchone()
        heard = self.db.execute(
            "SELECT COUNT(*) FROM pulse_hits h JOIN pulses p ON p.id = h.pulse_id "
            "WHERE p.lecture_id = ? AND h.student_id = ?", (lecture_id, student_id)).fetchone()[0]
        total = self.pulse_count(lecture_id)
        return {
            "checked_in": c is not None,
            "checked_in_at": c["at"] if c else None,
            "method": c["method"] if c else "",
            "pulses_heard": heard,
            "pulses_total": total,
            "status": attendance_status(c is not None, heard, total),
        }

    def heard_pulse(self, pulse_id: int, student_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM pulse_hits WHERE pulse_id = ? AND student_id = ?",
                               (pulse_id, student_id)).fetchone() is not None
