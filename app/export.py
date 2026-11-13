"""Offline spreadsheet: one Excel file with attendance per lecture, a semester overview, polls and comments."""
import datetime as dt
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

STATUS_FILL = {"Present": "C6EFCE", "Partial": "FFEB9C", "Absent": "FFC7CE"}


def _fmt(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


def _sheet(wb, title, header, rows):
    ws = wb.create_sheet(title[:31])
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(r)
    for i, h in enumerate(header, 1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows if i - 1 < len(r)])
        ws.column_dimensions[get_column_letter(i)].width = min(60, width + 2)
    ws.freeze_panes = "A2"
    return ws


class ExcelExporter:
    def __init__(self, roster, attendance, devices, polls, comments):
        self.roster, self.attendance, self.devices = roster, attendance, devices
        self.polls, self.comments = polls, comments

    def build(self) -> bytes:
        wb = Workbook()
        wb.remove(wb.active)
        students, lectures = self.roster.all(), self.attendance.lectures()

        # Overview: students x lectures
        header = ["Key", "Name"] + [f"#{l['id']} {l['title']}" for l in lectures] + ["Present", "Rate"]
        rows = []
        for s in students:
            statuses = [self.attendance.student_summary(l["id"], s.student_id)["status"] for l in lectures]
            present = sum(st == "Present" for st in statuses)
            rows.append([s.student_id, s.name, *statuses, present,
                         f"{round(100 * present / len(lectures))}%" if lectures else ""])
        ws = _sheet(wb, "Overview", header, rows)
        for row in ws.iter_rows(min_row=2, min_col=3, max_col=2 + len(lectures)):
            for c in row:
                if c.value in STATUS_FILL:
                    c.fill = PatternFill("solid", fgColor=STATUS_FILL[c.value])

        # One sheet per lecture
        for l in lectures:
            rows = []
            for s in students:
                sm = self.attendance.student_summary(l["id"], s.student_id)
                rows.append([s.student_id, s.name, sm["status"], _fmt(sm["checked_in_at"]), sm["method"],
                             f"{sm['pulses_heard']}/{sm['pulses_total']}",
                             "yes" if self.devices.is_registered(s.student_id) else ""])
            ws = _sheet(wb, f"L{l['id']} {l['title']}",
                        ["Key", "Name", "Status", "Checked in", "Method", "Pulses", "Phone registered"], rows)
            for row in ws.iter_rows(min_row=2, min_col=3, max_col=3):
                for c in row:
                    if c.value in STATUS_FILL:
                        c.fill = PatternFill("solid", fgColor=STATUS_FILL[c.value])

        poll_rows, comment_rows = [], []
        for l in lectures:
            for p in self.polls.all_for(l["id"]):
                poll_rows.append([l["title"], p["question"],
                                  " | ".join(f"{o}: {n}" for o, n in zip(p["options"], p["counts"])), p["total"]])
            for c in reversed(self.comments.for_lecture(l["id"])):
                comment_rows.append([l["title"], _fmt(c["at"]), c["author"], c["text"]])
        _sheet(wb, "Polls", ["Lecture", "Question", "Results", "Votes"], poll_rows)
        _sheet(wb, "Comments", ["Lecture", "Time", "Author", "Comment"], comment_rows)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
