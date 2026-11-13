"""Course roster: who may check in. Loaded from a file, not from Moodle (see docs/CONCEPT.md).

The lecturer's real list has **names only**: student ID numbers were removed for privacy (assignment Q&A #6).
So every student gets an internal key derived from the name, and an ID column is used only if a file has one.
"""
import csv
import hashlib
import io
import sqlite3
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
    """Stable internal key, so re-importing the same list keeps past attendance attached."""
    return "N" + hashlib.sha1(normalize_name(name).encode("utf-8")).hexdigest()[:10]


class RosterSource(ABC):
    """Where the student list comes from. A Moodle-backed source could be added later (Open/Closed)."""

    @abstractmethod
    def load(self) -> list[Student]: ...


class CsvRosterSource(RosterSource):
    """CSV with a header row: one full-name column, or first + last name columns. An ID column is optional."""

    ID_HEADERS = ("student_id", "id", "student id", "student number", "ת.ז", "תז", "מספר סטודנט")
    NAME_HEADERS = ("name", "full name", "full_name", "student name", "שם", "שם מלא", "שם הסטודנט")
    FIRST_HEADERS = ("first name", "first_name", "firstname", "שם פרטי")
    LAST_HEADERS = ("last name", "last_name", "lastname", "surname", "שם משפחה")

    def __init__(self, text: str):
        self.text = text.lstrip("﻿")  # Excel adds a BOM

    def load(self) -> list[Student]:
        reader = csv.DictReader(io.StringIO(self.text))
        headers = {h.strip().lower(): h for h in (reader.fieldnames or []) if h}
        pick = lambda options: next((headers[h] for h in options if h in headers), None)
        id_col, name_col = pick(self.ID_HEADERS), pick(self.NAME_HEADERS)
        first_col, last_col = pick(self.FIRST_HEADERS), pick(self.LAST_HEADERS)
        if not name_col and not (first_col and last_col):
            raise ValueError(f"CSV needs a name column (or first + last name), got: {list(headers)}")

        students, seen = [], set()
        for row in reader:
            get = lambda col: (row.get(col) or "").strip() if col else ""
            name = get(name_col) or f"{get(first_col)} {get(last_col)}".strip()
            name = " ".join(name.split())
            if not name:
                continue
            if normalize_name(name) in seen:
                raise ValueError(f"The name '{name}' appears twice — add something to tell them apart")
            seen.add(normalize_name(name))
            students.append(Student(get(id_col) or key_for_name(name), name))
        return students


class CourseRoster:
    """The students stored for the course."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def replace_all(self, source: RosterSource) -> int:
        students = source.load()
        for s in students:
            self.db.execute(
                "INSERT INTO students(student_id, name) VALUES (?, ?) "
                "ON CONFLICT(student_id) DO UPDATE SET name = excluded.name",
                (s.student_id, s.name),
            )
        return len(students)

    def all(self) -> list[Student]:
        rows = self.db.execute("SELECT student_id, name FROM students ORDER BY name").fetchall()
        return [Student(r["student_id"], r["name"]) for r in rows]

    def get(self, student_id: str) -> Student | None:
        r = self.db.execute("SELECT student_id, name FROM students WHERE student_id = ?", (student_id,)).fetchone()
        return Student(r["student_id"], r["name"]) if r else None

    def find_by_name(self, name: str) -> Student | None:
        """Exact match after normalising spaces and letter case."""
        wanted = normalize_name(name)
        return next((s for s in self.all() if normalize_name(s.name) == wanted), None)
