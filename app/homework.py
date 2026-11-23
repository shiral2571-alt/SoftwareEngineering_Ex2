"""Assignments and student submissions with an AI review (feature 5: "Students & teachers can get a deep
review (LLM) of their homework, including comparisons to other students' work"). SRS FR-7.16–7.21.

The lecturer uploads an assignment (optionally with a deadline). A student uploads their work and gets a
review from the AI, which sees the assignment, the student's work, and up to PEER_LIMIT other recent
submissions — compared only in general terms, never revealing another student's work (D-22).
"""
import sqlite3
import time

from .llm import LLMClient, OfflineClient

PEER_LIMIT = 5            # other submissions the AI sees (D-22: enough to compare, small enough to stay short)
PEER_CHARS = 6_000        # each peer submission is shortened to this
SUBMISSION_CHARS = 60_000
INSTRUCTIONS_CHARS = 20_000


class AssignmentService:
    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    # ----- lecturer -----
    def create(self, course_id: int, title: str, instructions: str, deadline: float | None = None) -> int:
        if not title.strip():
            raise ValueError("Assignment title is required")
        if not instructions.strip():
            raise ValueError("Upload or paste the assignment itself")
        return self.db.execute(
            "INSERT INTO assignments(course_id, title, instructions, deadline, created_at) VALUES (?, ?, ?, ?, ?)",
            (course_id, title.strip(), instructions.strip(), deadline, self.clock())).lastrowid

    def delete(self, assignment_id: int) -> None:
        self.db.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))

    def get(self, assignment_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
        return dict(r) if r else None

    def of_course(self, course_id: int) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT a.*, (SELECT COUNT(*) FROM submissions s WHERE s.assignment_id = a.id) AS submitted "
            "FROM assignments a WHERE a.course_id = ? ORDER BY a.id DESC", (course_id,))]

    def submissions(self, assignment_id: int) -> list[dict]:
        """Everything for the lecturer: who, when, late or not, and the review the student got."""
        a = self.get(assignment_id)
        rows = self.db.execute(
            "SELECT s.student_id, st.name, s.filename, s.submitted_at, s.review, s.engine "
            "FROM submissions s JOIN students st ON st.student_id = s.student_id "
            "WHERE s.assignment_id = ? ORDER BY s.submitted_at DESC", (assignment_id,)).fetchall()
        return [{**dict(r), "late": is_late(a, r["submitted_at"])} for r in rows]

    # ----- student -----
    def for_student(self, course_ids: list[int], student_id: str) -> list[dict]:
        if not course_ids:
            return []
        marks = ",".join("?" * len(course_ids))
        out = []
        for a in self.db.execute(f"SELECT a.*, c.name AS course FROM assignments a JOIN courses c ON c.id = a.course_id "
                                 f"WHERE a.course_id IN ({marks}) ORDER BY a.id DESC", course_ids):
            mine = self.my_submission(a["id"], student_id)
            out.append({"id": a["id"], "title": a["title"], "course": a["course"], "deadline": a["deadline"],
                        "instructions": a["instructions"], "submission": mine})
        return out

    def my_submission(self, assignment_id: int, student_id: str) -> dict | None:
        r = self.db.execute("SELECT filename, submitted_at, review, engine FROM submissions "
                            "WHERE assignment_id = ? AND student_id = ?", (assignment_id, student_id)).fetchone()
        if r is None:
            return None
        return {**dict(r), "late": is_late(self.get(assignment_id), r["submitted_at"])}

    def submit(self, assignment_id: int, student_id: str, filename: str, content: str) -> None:
        """Submitting again replaces the earlier submission; the date shown is always the latest (D-23)."""
        if not content.strip():
            raise ValueError("The file is empty")
        self.db.execute(
            "INSERT INTO submissions(assignment_id, student_id, filename, content, submitted_at, review, engine) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL) ON CONFLICT(assignment_id, student_id) DO UPDATE SET "
            "filename = excluded.filename, content = excluded.content, submitted_at = excluded.submitted_at, "
            "review = NULL, engine = NULL",
            (assignment_id, student_id, filename, content[:SUBMISSION_CHARS], self.clock()))

    def submission_text(self, assignment_id: int, student_id: str) -> str:
        r = self.db.execute("SELECT content FROM submissions WHERE assignment_id = ? AND student_id = ?",
                            (assignment_id, student_id)).fetchone()
        return r["content"] if r else ""

    def peers(self, assignment_id: int, student_id: str, limit: int = PEER_LIMIT) -> list[str]:
        """The most recent other submissions, as text only — no names ever reach the AI."""
        rows = self.db.execute("SELECT content FROM submissions WHERE assignment_id = ? AND student_id != ? "
                               "ORDER BY submitted_at DESC LIMIT ?", (assignment_id, student_id, limit))
        return [r["content"][:PEER_CHARS] for r in rows]

    def save_review(self, assignment_id: int, student_id: str, review: str, engine: str) -> None:
        self.db.execute("UPDATE submissions SET review = ?, engine = ? WHERE assignment_id = ? AND student_id = ?",
                        (review, engine, assignment_id, student_id))


def is_late(assignment: dict | None, submitted_at: float) -> bool:
    return bool(assignment and assignment["deadline"] and submitted_at > assignment["deadline"])


# ------------------------------------------------------------------ the AI review the student gets
STUDENT_REVIEW_PROMPT = """You are a teaching assistant. You receive: the assignment as the lecturer wrote it, \
ONE student's submission, and some other students' submissions to the same assignment (anonymous, for \
comparison only). Write feedback to this student.

**Write the whole review in Hebrew**, in short Markdown, with exactly these sections and headings:

### 1. עמידה בדרישות המטלה
Which requirements of the assignment the submission meets, and which are missing or partial.

### 2. חוזקות
### 3. מה לשפר
Concrete and actionable.

### 4. בהשוואה לכיתה
How this submission compares to the others in general terms only: what most or some of the class did that \
this student did not, or where this student is stronger than most.

Rules:
- NEVER quote, copy, paraphrase or describe the content of a specific other submission, and never reveal \
another student's answer or solution. Only general patterns ("most of the class…", "a few submissions…").
- If there are fewer than two other submissions, say that the comparison is limited.
- Never invent facts. If a fact in the submission seems doubtful (dates, names, events, sources), mark it \
"לבדיקה" instead of stating it is wrong.
- Do not give a grade. The lecturer grades.
- Be brief and kind."""


def review_submission(assignment: str, submission: str, peers: list[str], llm: LLMClient) -> tuple[str, str]:
    """Returns (review markdown, engine name). Offline: a short note instead of failing (FR-7.4)."""
    header = lambda engine: f"**Model:** {engine}"
    if isinstance(llm, OfflineClient):
        return (f"{header(llm.name)}\n\nYour work was submitted. An AI review needs an AI key, which the "
                f"lecturer can add in Settings.", llm.name)
    peers_text = "\n\n".join(f"--- Other submission {i + 1} ---\n{p}" for i, p in enumerate(peers)) or "(none yet)"
    prompt = (f"=== ASSIGNMENT ===\n{assignment[:INSTRUCTIONS_CHARS]}\n\n"
              f"=== THIS STUDENT'S SUBMISSION ===\n{submission}\n\n"
              f"=== OTHER SUBMISSIONS ({len(peers)}) — for comparison only, never reveal ===\n{peers_text}")
    try:
        return f"{header(llm.name)}\n\n{llm.complete(STUDENT_REVIEW_PROMPT, prompt)}", llm.name
    except Exception as e:  # no internet in class, bad key → the submission still counts
        return (f"{header(llm.name)} — AI unavailable ({e.__class__.__name__}).\n\n"
                f"Your work was submitted; try the review again later.", llm.name)
