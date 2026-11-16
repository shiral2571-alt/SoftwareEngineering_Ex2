"""Courses and their rosters. Loaded from a file, not from Moodle (SRS CON-1, FR-2.x).

The lecturer's real list has **names only**: student ID numbers were removed for privacy (SRS D-3).
Every student gets an internal key derived from the name; an ID column is used only if a file has one.
A student who appears in two courses is the same person (same name → same key → same phone).
"""
import csv
import hashlib
import io
import sqlite3
import time
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Student:
    student_id: str  # internal key; the real ID number only if the file provides one
    name: str


def normalize_name(name: str) -> str:
    """'  noa   LEVI ' and 'Noa Levi' are the same person."""
    return " ".join(unicodedata.normalize("NFC", name).split()).casefold()


def key_for_name(name: str) -> str:
    """Stable internal key, so re-importing the same list keeps past attendance attached (FR-2.3)."""
    return "N" + hashlib.sha1(normalize_name(name).encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ sources (Open/Closed: add Moodle later)
class RosterSource(ABC):
    """Where a student list comes from."""

    @abstractmethod
    def load(self) -> list[Student]: ...


class TableRosterSource(RosterSource):
    """Rows with a header: one full-name column, or first + last name columns. An ID column is optional."""

    ID_HEADERS = ("student_id", "id", "student id", "student number", "ת.ז", "תז", "מספר סטודנט")
    NAME_HEADERS = ("name", "full name", "full_name", "student name", "שם", "שם מלא", "שם הסטודנט")
    FIRST_HEADERS = ("first name", "first_name", "firstname", "שם פרטי")
    LAST_HEADERS = ("last name", "last_name", "lastname", "surname", "שם משפחה")

    def __init__(self, header: list[str], rows: list[list[str]]):
        self.header, self.rows = header, rows

    def load(self) -> list[Student]:
        cols = {str(h).strip().lower(): i for i, h in enumerate(self.header) if h is not None and str(h).strip()}
        pick = lambda options: next((cols[h] for h in options if h in cols), None)
        id_col, name_col = pick(self.ID_HEADERS), pick(self.NAME_HEADERS)
        first_col, last_col = pick(self.FIRST_HEADERS), pick(self.LAST_HEADERS)
        if name_col is None and (first_col is None or last_col is None):
            raise ValueError(f"The file needs a name column (or first + last name), got: {list(cols)}")

        students, seen = [], set()
        for row in self.rows:
            get = lambda i: (str(row[i]).strip() if i is not None and i < len(row) and row[i] is not None else "")
            name = get(name_col) or f"{get(first_col)} {get(last_col)}".strip()
            name = " ".join(name.split())
            if not name:
                continue
            if normalize_name(name) in seen:
                raise ValueError(f"The name '{name}' appears twice — add something to tell them apart")
            seen.add(normalize_name(name))
            students.append(Student(get(id_col) or key_for_name(name), name))
        return students


class CsvRosterSource(TableRosterSource):
    def __init__(self, text: str):
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))  # Excel adds a BOM
        super().__init__(rows[0] if rows else [], rows[1:])


class XlsxRosterSource(TableRosterSource):
    def __init__(self, data: bytes):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        super().__init__(rows[0] if rows else [], rows[1:])


def roster_source_for(filename: str, data: bytes) -> RosterSource:
    """Factory: pick the parser by file extension."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        return XlsxRosterSource(data)
    return CsvRosterSource(data.decode("utf-8-sig"))


# ------------------------------------------------------------------ courses
class CourseService:
    def __init__(self, db: sqlite3.Connection, clock=time.time):
        self.db, self.clock = db, clock

    def create(self, name: str) -> int:
        if not name.strip():
            raise ValueError("Course name is required")
        return self.db.execute("INSERT INTO courses(name, created_at) VALUES (?, ?)",
                               (name.strip(), self.clock())).lastrowid

    def all(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS students "
            "FROM courses c ORDER BY c.id")]

    def get(self, course_id: int) -> dict | None:
        r = self.db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        return dict(r) if r else None


class CourseRoster:
    """Students and enrollments."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def import_into(self, course_id: int, source: RosterSource) -> int:
        """Add the file's students to the course (existing students and their history are kept)."""
        students = source.load()
        for s in students:
            self.db.execute("INSERT INTO students(student_id, name) VALUES (?, ?) "
                            "ON CONFLICT(student_id) DO UPDATE SET name = excluded.name", (s.student_id, s.name))
            self.db.execute("INSERT OR IGNORE INTO enrollments(course_id, student_id) VALUES (?, ?)",
                            (course_id, s.student_id))
        return len(students)

    def students_of(self, course_id: int) -> list[Student]:
        rows = self.db.execute("SELECT s.student_id, s.name FROM students s JOIN enrollments e "
                               "ON e.student_id = s.student_id WHERE e.course_id = ? ORDER BY s.name", (course_id,))
        return [Student(r["student_id"], r["name"]) for r in rows]

    def is_enrolled(self, course_id: int, student_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM enrollments WHERE course_id = ? AND student_id = ?",
                               (course_id, student_id)).fetchone() is not None

    def courses_of(self, student_id: str) -> list[int]:
        return [r[0] for r in self.db.execute("SELECT course_id FROM enrollments WHERE student_id = ?", (student_id,))]

    def all_names(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT name FROM students ORDER BY name")]

    def get(self, student_id: str) -> Student | None:
        r = self.db.execute("SELECT student_id, name FROM students WHERE student_id = ?", (student_id,)).fetchone()
        return Student(r["student_id"], r["name"]) if r else None

    def find_by_name(self, name: str) -> Student | None:
        """Exact match after normalising spaces and letter case."""
        wanted = normalize_name(name)
        for r in self.db.execute("SELECT student_id, name FROM students"):
            if normalize_name(r["name"]) == wanted:
                return Student(r["student_id"], r["name"])
        return None
