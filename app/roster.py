"""Course roster: who may check in. Loaded from a file, not from Moodle (see docs/CONCEPT.md)."""
import csv
import io
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Student:
    student_id: str
    name: str


class RosterSource(ABC):
    """Where the student list comes from. A Moodle-backed source could be added later (Open/Closed)."""

    @abstractmethod
    def load(self) -> list[Student]: ...


class CsvRosterSource(RosterSource):
    """CSV text with a header row. Accepts columns like 'student_id'/'id' and 'name'/'full name'."""

    ID_HEADERS = ("student_id", "id", "student id", "student number", "ת.ז", "תז", "מספר סטודנט")
    NAME_HEADERS = ("name", "full name", "full_name", "student name", "שם", "שם מלא")

    def __init__(self, text: str):
        self.text = text.lstrip("﻿")  # Excel adds a BOM

    def load(self) -> list[Student]:
        reader = csv.DictReader(io.StringIO(self.text))
        headers = {h.strip().lower(): h for h in (reader.fieldnames or [])}
        id_col = next((headers[h] for h in self.ID_HEADERS if h in headers), None)
        name_col = next((headers[h] for h in self.NAME_HEADERS if h in headers), None)
        if not id_col or not name_col:
            raise ValueError(f"CSV needs an ID column and a name column, got: {list(headers)}")
        students = []
        for row in reader:
            sid, name = (row.get(id_col) or "").strip(), (row.get(name_col) or "").strip()
            if sid and name:
                students.append(Student(sid, name))
        return students


class CourseRoster:
    """The students stored for the course, plus identity checks."""

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

    def verify(self, name: str, id_last4: str) -> Student | None:
        """Pick-your-name + last 4 digits of the student ID. Returns the student or None."""
        name, id_last4 = name.strip().casefold(), id_last4.strip()
        if len(id_last4) != 4 or not id_last4.isdigit():
            return None
        for s in self.all():
            if s.name.casefold() == name and s.student_id.endswith(id_last4):
                return s
        return None
