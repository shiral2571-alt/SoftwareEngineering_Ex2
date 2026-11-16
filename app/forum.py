"""Per-lecture forum: questions and comments, lecturer replies, 👍 "me too" (SRS FR-6.x).

Anonymous posts are **fully anonymous** (D-8): no student reference is stored, not even for the lecturer.
"""
import sqlite3
import time

MAX_POST = 1000


class ForumService:
    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    def post(self, lecture_id: int, student_id: str, text: str, anonymous: bool) -> int:
        text = text.strip()
        if not text:
            raise ValueError("Empty post")
        return self.db.execute("INSERT INTO posts(lecture_id, student_id, text, at) VALUES (?, ?, ?, ?)",
                               (lecture_id, None if anonymous else student_id, text[:MAX_POST], self.clock())).lastrowid

    def reply(self, post_id: int, text: str) -> int:
        """Lecturer reply; students see it under the post."""
        if not text.strip():
            raise ValueError("Empty reply")
        return self.db.execute("INSERT INTO replies(post_id, text, at) VALUES (?, ?, ?)",
                               (post_id, text.strip()[:MAX_POST], self.clock())).lastrowid

    def delete_post(self, post_id: int) -> None:
        self.db.execute("DELETE FROM posts WHERE id = ?", (post_id,))

    def delete_reply(self, reply_id: int) -> None:
        self.db.execute("DELETE FROM replies WHERE id = ?", (reply_id,))

    def toggle_upvote(self, post_id: int, student_id: str) -> bool:
        """Returns True if the student now upvotes the post."""
        cur = self.db.execute("DELETE FROM upvotes WHERE post_id = ? AND student_id = ?", (post_id, student_id))
        if cur.rowcount:
            return False
        self.db.execute("INSERT INTO upvotes(post_id, student_id) VALUES (?, ?)", (post_id, student_id))
        return True

    def of_lecture(self, lecture_id: int, viewer_id: str | None = None) -> list[dict]:
        """Most-upvoted first, then newest. `viewer_id` marks the viewer's own upvotes and posts."""
        rows = self.db.execute(
            "SELECT p.*, s.name, (SELECT COUNT(*) FROM upvotes u WHERE u.post_id = p.id) AS votes "
            "FROM posts p LEFT JOIN students s ON s.student_id = p.student_id "
            "WHERE p.lecture_id = ? ORDER BY votes DESC, p.id DESC", (lecture_id,)).fetchall()
        out = []
        for r in rows:
            replies = [dict(x) for x in self.db.execute("SELECT id, text, at FROM replies WHERE post_id = ? ORDER BY id",
                                                        (r["id"],))]
            item = {"id": r["id"], "text": r["text"], "at": r["at"], "votes": r["votes"], "replies": replies,
                    "author": r["name"] if r["student_id"] else "Anonymous"}
            if viewer_id:
                item["upvoted"] = self.db.execute("SELECT 1 FROM upvotes WHERE post_id = ? AND student_id = ?",
                                                  (r["id"], viewer_id)).fetchone() is not None
                item["mine"] = r["student_id"] == viewer_id
            out.append(item)
        return out
