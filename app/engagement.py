"""KISS polls and comments/suggestions."""
import json
import sqlite3
import time

MAX_COMMENT = 500


class PollService:
    """One open poll at a time, 2–4 options, one vote per student (KISS)."""

    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    def create(self, lecture_id: int, question: str, options: list[str]) -> int:
        options = [o.strip() for o in options if o and o.strip()]
        if not question.strip() or not 2 <= len(options) <= 4:
            raise ValueError("A poll needs a question and 2–4 options")
        self.db.execute("UPDATE polls SET is_open = 0 WHERE lecture_id = ?", (lecture_id,))
        cur = self.db.execute("INSERT INTO polls(lecture_id, question, options, created_at) VALUES (?, ?, ?, ?)",
                              (lecture_id, question.strip(), json.dumps(options), self.clock()))
        return cur.lastrowid

    def close(self, poll_id: int) -> None:
        self.db.execute("UPDATE polls SET is_open = 0 WHERE id = ?", (poll_id,))

    def open_poll(self, lecture_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM polls WHERE lecture_id = ? AND is_open = 1 ORDER BY id DESC LIMIT 1",
                            (lecture_id,)).fetchone()
        return self._to_dict(r) if r else None

    def latest(self, lecture_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM polls WHERE lecture_id = ? ORDER BY id DESC LIMIT 1", (lecture_id,)).fetchone()
        return self._to_dict(r) if r else None

    def all_for(self, lecture_id: int) -> list[dict]:
        rows = self.db.execute("SELECT * FROM polls WHERE lecture_id = ? ORDER BY id", (lecture_id,)).fetchall()
        return [self._to_dict(r) for r in rows]

    def vote(self, poll_id: int, student_id: str, option_index: int) -> bool:
        r = self.db.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()
        if r is None or not r["is_open"] or not 0 <= option_index < len(json.loads(r["options"])):
            return False
        cur = self.db.execute("INSERT OR IGNORE INTO votes(poll_id, student_id, option_index) VALUES (?, ?, ?)",
                              (poll_id, student_id, option_index))
        return cur.rowcount == 1

    def has_voted(self, poll_id: int, student_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM votes WHERE poll_id = ? AND student_id = ?",
                               (poll_id, student_id)).fetchone() is not None

    def _to_dict(self, r: sqlite3.Row) -> dict:
        options = json.loads(r["options"])
        counts = [0] * len(options)
        for v in self.db.execute("SELECT option_index, COUNT(*) n FROM votes WHERE poll_id = ? GROUP BY option_index",
                                 (r["id"],)):
            counts[v["option_index"]] = v["n"]
        return {"id": r["id"], "question": r["question"], "options": options, "counts": counts,
                "total": sum(counts), "is_open": bool(r["is_open"])}


class CommentService:
    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    def add(self, lecture_id: int, student_id: str, text: str, anonymous: bool) -> None:
        text = text.strip()
        if not text:
            raise ValueError("Empty comment")
        self.db.execute("INSERT INTO comments(lecture_id, student_id, anonymous, text, at) VALUES (?, ?, ?, ?, ?)",
                        (lecture_id, student_id, int(anonymous), text[:MAX_COMMENT], self.clock()))

    def for_lecture(self, lecture_id: int) -> list[dict]:
        rows = self.db.execute(
            "SELECT c.*, s.name FROM comments c LEFT JOIN students s ON s.student_id = c.student_id "
            "WHERE c.lecture_id = ? ORDER BY c.id DESC", (lecture_id,)).fetchall()
        return [{"id": r["id"], "text": r["text"], "at": r["at"],
                 "author": "Anonymous" if r["anonymous"] else (r["name"] or "?")} for r in rows]
