"""Polls: a set of questions, prepared in advance and launched with one click (SRS FR-5.x).

Question kinds:
- quiz   — multiple choice with a correct answer (never free text)
- choice — multiple choice without a correct answer (feedback)
- text   — free-text answer (feedback only)
"""
import csv
import io
import json
import sqlite3
import time
from dataclasses import dataclass, field

QUIZ, CHOICE, TEXT = "quiz", "choice", "text"
KINDS = (QUIZ, CHOICE, TEXT)
MAX_OPTIONS = 6
MAX_TEXT_ANSWER = 500
TEMPLATE_HEADER = ["question", "type", "option1", "option2", "option3", "option4", "correct"]


@dataclass
class Question:
    text: str
    kind: str = CHOICE
    options: list[str] = field(default_factory=list)
    correct: int | None = None  # 0-based option index, quiz only

    def validate(self) -> "Question":
        self.text = self.text.strip()
        self.options = [o.strip() for o in self.options if o and str(o).strip()]
        if not self.text:
            raise ValueError("A question needs text")
        if self.kind not in KINDS:
            raise ValueError(f"Question type must be one of {KINDS}")
        if self.kind == TEXT:
            self.options, self.correct = [], None
            return self
        if not 2 <= len(self.options) <= MAX_OPTIONS:
            raise ValueError(f"'{self.text}': multiple choice needs 2–{MAX_OPTIONS} options")
        if self.kind == QUIZ:
            if self.correct is None or not 0 <= self.correct < len(self.options):
                raise ValueError(f"'{self.text}': a quiz question needs a valid correct answer")
        else:
            self.correct = None
        return self


class PollService:
    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    # ----- authoring (lecturer) -----
    def create(self, lecture_id: int, title: str, questions: list[Question], show_correct: bool = False) -> int:
        if not questions:
            raise ValueError("A poll needs at least one question")
        questions = [q.validate() for q in questions]
        pid = self.db.execute("INSERT INTO polls(lecture_id, title, show_correct, created_at) VALUES (?, ?, ?, ?)",
                              (lecture_id, title.strip() or "Poll", int(show_correct), self.clock())).lastrowid
        for pos, q in enumerate(questions):
            self.db.execute("INSERT INTO questions(poll_id, position, text, kind, options, correct) VALUES (?, ?, ?, ?, ?, ?)",
                            (pid, pos, q.text, q.kind, json.dumps(q.options, ensure_ascii=False), q.correct))
        return pid

    def launch(self, poll_id: int) -> None:
        """Make the poll visible to students (one click during the lecture, or later)."""
        self.db.execute("UPDATE polls SET state = 'live' WHERE id = ?", (poll_id,))

    def close(self, poll_id: int) -> None:
        self.db.execute("UPDATE polls SET state = 'closed' WHERE id = ?", (poll_id,))

    def delete(self, poll_id: int) -> None:
        self.db.execute("DELETE FROM polls WHERE id = ?", (poll_id,))

    def set_show_correct(self, poll_id: int, show: bool) -> None:
        self.db.execute("UPDATE polls SET show_correct = ? WHERE id = ?", (int(show), poll_id))

    # ----- answering (student) -----
    def answer(self, question_id: int, student_id: str, option_index: int | None = None, text: str | None = None) -> bool:
        q = self.db.execute("SELECT q.*, p.state FROM questions q JOIN polls p ON p.id = q.poll_id WHERE q.id = ?",
                            (question_id,)).fetchone()
        if q is None or q["state"] != "live":
            return False
        if q["kind"] == TEXT:
            text = (text or "").strip()[:MAX_TEXT_ANSWER]
            if not text:
                return False
            option_index = None
        else:
            if option_index is None or not 0 <= option_index < len(json.loads(q["options"])):
                return False
            text = None
        cur = self.db.execute("INSERT OR IGNORE INTO answers(question_id, student_id, option_index, text, at) "
                              "VALUES (?, ?, ?, ?, ?)", (question_id, student_id, option_index, text, self.clock()))
        return cur.rowcount == 1  # one answer per student per question

    # ----- reading -----
    def of_lecture(self, lecture_id: int, live_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM polls WHERE lecture_id = ?" + (" AND state = 'live'" if live_only else "")
        return [self._poll(r) for r in self.db.execute(sql + " ORDER BY id", (lecture_id,))]

    def for_student(self, lecture_id: int, student_id: str) -> list[dict]:
        """Live polls without results; the student's own answers; the correct answer only if allowed and answered."""
        out = []
        for p in self.of_lecture(lecture_id, live_only=True):
            qs = []
            for q in p["questions"]:
                mine = self.db.execute("SELECT option_index, text FROM answers WHERE question_id = ? AND student_id = ?",
                                       (q["id"], student_id)).fetchone()
                item = {k: q[k] for k in ("id", "text", "kind", "options")}
                item["answered"] = mine is not None
                item["my_option"] = mine["option_index"] if mine else None
                if mine and q["kind"] == QUIZ and p["show_correct"]:
                    item["correct"] = q["correct"]
                qs.append(item)
            out.append({"id": p["id"], "title": p["title"], "questions": qs})
        return out

    def _poll(self, r: sqlite3.Row) -> dict:
        questions = []
        for q in self.db.execute("SELECT * FROM questions WHERE poll_id = ? ORDER BY position", (r["id"],)):
            options = json.loads(q["options"])
            counts = [0] * len(options)
            texts = []
            for a in self.db.execute("SELECT option_index, text FROM answers WHERE question_id = ?", (q["id"],)):
                if a["option_index"] is not None:
                    counts[a["option_index"]] += 1
                elif a["text"]:
                    texts.append(a["text"])
            total = sum(counts) + len(texts)
            item = {"id": q["id"], "text": q["text"], "kind": q["kind"], "options": options, "correct": q["correct"],
                    "counts": counts, "texts": texts, "total": total}
            if q["kind"] == QUIZ:
                item["percent_correct"] = round(100 * counts[q["correct"]] / total) if total else None
            questions.append(item)
        return {"id": r["id"], "title": r["title"], "state": r["state"], "show_correct": bool(r["show_correct"]),
                "questions": questions}


# ------------------------------------------------------------------ import from a file (FR-5.6)
def parse_poll_file(filename: str, data: bytes) -> list[Question]:
    """Read questions from the template: question, type, option1..option4, correct.

    type    — quiz | choice | text   (empty = choice)
    correct — the number (1–4) or the exact text of the right option; quiz only
    """
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        rows = [["" if v is None else str(v) for v in r] for r in ws.iter_rows(values_only=True)]
    else:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("The file is empty")
    header = [h.strip().lower() for h in rows[0]]
    if "question" not in header:
        raise ValueError(f"The first row must be the template header: {', '.join(TEMPLATE_HEADER)}")
    col = {h: i for i, h in enumerate(header)}
    get = lambda row, name: row[col[name]].strip() if name in col and col[name] < len(row) else ""

    questions = []
    for n, row in enumerate(rows[1:], start=2):
        if not get(row, "question"):
            continue
        options = [get(row, h) for h in header if h.startswith("option")]
        options = [o for o in options if o]
        kind = (get(row, "type") or CHOICE).lower()
        correct_raw, correct = get(row, "correct"), None
        if correct_raw:
            if correct_raw.isdigit():
                correct = int(correct_raw) - 1
            elif correct_raw in options:
                correct = options.index(correct_raw)
        try:
            questions.append(Question(get(row, "question"), kind, options, correct).validate())
        except ValueError as e:
            raise ValueError(f"Row {n}: {e}") from None
    if not questions:
        raise ValueError("No questions found in the file")
    return questions


def template_csv() -> str:
    """The downloadable template, with one example of each question type."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEMPLATE_HEADER)
    w.writerow(["Which principle says 'open for extension, closed for modification'?", "quiz",
                "Single responsibility", "Open/Closed", "Liskov substitution", "Dependency inversion", "2"])
    w.writerow(["How clear was today's lecture?", "choice", "Very clear", "Mostly clear", "Confusing", "", ""])
    w.writerow(["What should I explain again next time?", "text", "", "", "", "", ""])
    return buf.getvalue()
