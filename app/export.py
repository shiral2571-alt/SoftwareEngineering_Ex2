"""Offline spreadsheet (FR-4.11): one Excel file per course — overview, one sheet per lecture, polls, forum."""
import datetime as dt
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

LABEL = {"present": "Present", "late": "Late", "absent": "Absent"}
FILL = {"Present": "C6EFCE", "Late": "FFEB9C", "Absent": "FFC7CE"}


def _fmt(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


def _sheet(wb, title, header, rows, status_cols=()):
    ws = wb.create_sheet(title[:31].replace("/", "-"))
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(r)
    for i, h in enumerate(header, 1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows if i - 1 < len(r)])
        ws.column_dimensions[get_column_letter(i)].width = min(60, width + 2)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if c.column in status_cols and c.value in FILL:
                c.fill = PatternFill("solid", fgColor=FILL[c.value])
    ws.freeze_panes = "A2"
    return ws


class ExcelExporter:
    def __init__(self, courses, roster, lectures, attendance, polls, forum):
        self.courses, self.roster, self.lectures = courses, roster, lectures
        self.attendance, self.polls, self.forum = attendance, polls, forum

    def build(self, course_id: int) -> bytes:
        wb = Workbook()
        wb.remove(wb.active)
        students = self.roster.students_of(course_id)
        lectures = [l for l in reversed(self.lectures.of_course(course_id)) if l["state"] != "draft"]

        # Overview: students × lectures
        header = ["Name"] + [f"#{l['id']} {l['title']}" for l in lectures] + ["Present", "Late", "Rate"]
        rows = []
        for s in students:
            st = [LABEL[self.attendance.status_of(l["id"], s.student_id)] for l in lectures]
            present, late = st.count("Present"), st.count("Late")
            rows.append([s.name, *st, present, late,
                         f"{round(100 * (present + late) / len(lectures))}%" if lectures else ""])
        _sheet(wb, "Overview", header, rows, status_cols=range(2, 2 + len(lectures)))

        poll_rows, forum_rows = [], []
        for l in lectures:
            sheet = self.attendance.sheet(l["id"], students)
            _sheet(wb, f"L{l['id']} {l['title']}", ["Name", "Status", "Time", "Method"],
                   [[r["name"], LABEL[r["status"]], _fmt(r["at"]), r["method"]] for r in sheet], status_cols=(2,))
            for p in self.polls.of_lecture(l["id"]):
                for q in p["questions"]:
                    if q["kind"] == "text":
                        result = " | ".join(q["texts"])
                    else:
                        result = " | ".join(f"{o}{' ✓' if i == q['correct'] else ''}: {n}"
                                            for i, (o, n) in enumerate(zip(q["options"], q["counts"])))
                    poll_rows.append([l["title"], p["title"], q["text"], q["kind"], result, q["total"],
                                      f"{q['percent_correct']}%" if q.get("percent_correct") is not None else ""])
            for post in self.forum.of_lecture(l["id"]):
                forum_rows.append([l["title"], _fmt(post["at"]), post["author"], post["text"], post["votes"],
                                   " / ".join(r["text"] for r in post["replies"])])
        _sheet(wb, "Polls", ["Lecture", "Poll", "Question", "Type", "Results", "Answers", "% correct"], poll_rows)
        _sheet(wb, "Forum", ["Lecture", "Time", "Author", "Post", "👍", "Lecturer reply"], forum_rows)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
