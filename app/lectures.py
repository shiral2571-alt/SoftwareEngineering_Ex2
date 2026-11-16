"""The lecture as an object with a lifecycle: Draft → Open → Closed, and Closed → Open again (SRS §3, FR-3.x)."""
import sqlite3
import time

DRAFT, OPEN, CLOSED = "draft", "open", "closed"

# Allowed state changes. Anything else is a programming or user error.
TRANSITIONS = {
    (DRAFT, OPEN): "opened_at",
    (OPEN, CLOSED): "closed_at",
    (CLOSED, OPEN): "opened_at",   # reopen, e.g. closed by mistake (FR-3.3)
}


class LectureStateError(ValueError):
    pass


class LectureService:
    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    def create(self, course_id: int, title: str) -> int:
        """New lectures start as Draft: only the lecturer sees them (FR-3.1)."""
        if not title.strip():
            raise ValueError("Lecture title is required")
        return self.db.execute("INSERT INTO lectures(course_id, title, state, created_at) VALUES (?, ?, ?, ?)",
                               (course_id, title.strip(), DRAFT, self.clock())).lastrowid

    def rename(self, lecture_id: int, title: str) -> None:
        if title.strip():
            self.db.execute("UPDATE lectures SET title = ? WHERE id = ?", (title.strip(), lecture_id))

    def _move(self, lecture_id: int, new_state: str) -> None:
        lec = self.get(lecture_id)
        if lec is None:
            raise LectureStateError("No such lecture")
        column = TRANSITIONS.get((lec["state"], new_state))
        if column is None:
            raise LectureStateError(f"Cannot change a {lec['state']} lecture to {new_state}")
        self.db.execute(f"UPDATE lectures SET state = ?, {column} = ? WHERE id = ?",
                        (new_state, self.clock(), lecture_id))

    def open(self, lecture_id: int) -> None:
        self._move(lecture_id, OPEN)

    def close(self, lecture_id: int) -> None:
        """Closing also ends any check-in window that is still open."""
        self._move(lecture_id, CLOSED)
        self.db.execute("UPDATE checkin_windows SET closed_at = ? WHERE lecture_id = ? AND closed_at IS NULL",
                        (self.clock(), lecture_id))

    def reopen(self, lecture_id: int) -> None:
        self._move(lecture_id, OPEN)

    def get(self, lecture_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
        return dict(r) if r else None

    def of_course(self, course_id: int) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM lectures WHERE course_id = ? ORDER BY id DESC", (course_id,))]

    def visible_to_student(self, course_ids: list[int]) -> list[dict]:
        """Students see Open and Closed lectures of their courses — never drafts."""
        if not course_ids:
            return []
        marks = ",".join("?" * len(course_ids))
        return [dict(r) for r in self.db.execute(
            f"SELECT l.*, c.name AS course FROM lectures l JOIN courses c ON c.id = l.course_id "
            f"WHERE l.course_id IN ({marks}) AND l.state != ? ORDER BY l.state = 'open' DESC, l.id DESC",
            (*course_ids, DRAFT))]


class MaterialService:
    """Files, notes and AI reports attached to a lecture (FR-3.5, FR-7.12)."""

    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    def add(self, lecture_id: int, kind: str, title: str, content: str, visible: bool = False) -> int:
        return self.db.execute(
            "INSERT INTO materials(lecture_id, kind, title, content, visible_to_students, at) VALUES (?, ?, ?, ?, ?, ?)",
            (lecture_id, kind, title.strip() or "Untitled", content, int(visible), self.clock())).lastrowid

    def of_lecture(self, lecture_id: int, students_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM materials WHERE lecture_id = ?" + (" AND visible_to_students = 1" if students_only else "")
        return [dict(r) for r in self.db.execute(sql + " ORDER BY id DESC", (lecture_id,))]

    def delete(self, material_id: int) -> None:
        self.db.execute("DELETE FROM materials WHERE id = ?", (material_id,))
