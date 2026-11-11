"""Web-based teaching tool — Flask application factory and HTTP routes.

Routes are thin: they read the request, call a service class, and return JSON/HTML.
All decisions (is this token valid? did this student vote?) live in the service classes.
"""
import os
import secrets
import time
from functools import wraps
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, send_file, session
import io

from . import db as dbmod
from .ai_tools import default_llm, review_homework, summarize_lecture
from .attendance import AttendanceService
from .engagement import CommentService, PollService
from .export import ExcelExporter
from .identity import DeviceRegistry
from .roster import CourseRoster, CsvRosterSource

DEVICE_COOKIE = "device"
DEVICE_COOKIE_AGE = 365 * 24 * 3600  # server-set HttpOnly cookie: survives Safari's 7-day script-storage cap
SAMPLE_ROSTER = Path(__file__).resolve().parent.parent / "data" / "sample_roster.csv"


def create_app(db_path: str = "teaching_tool.db", lecturer_pin: str | None = None, llm=None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
    app.config["LECTURER_PIN"] = lecturer_pin or os.environ.get("LECTURER_PIN") or f"{secrets.randbelow(10**6):06d}"

    conn = dbmod.connect(db_path)
    roster = CourseRoster(conn)
    devices = DeviceRegistry(conn, roster)
    attendance = AttendanceService(conn)
    polls, comments = PollService(conn), CommentService(conn)
    llm = llm or default_llm()
    if not roster.all() and SAMPLE_ROSTER.exists():
        roster.replace_all(CsvRosterSource(SAMPLE_ROSTER.read_text(encoding="utf-8")))
    app.extensions["services"] = dict(roster=roster, devices=devices, attendance=attendance, polls=polls,
                                      comments=comments, llm=llm)

    # ------------------------------------------------------------------ helpers
    def current_student():
        return devices.student_for(request.cookies.get(DEVICE_COOKIE))

    def lecturer_only(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if not session.get("lecturer"):
                abort(401)
            return f(*a, **kw)
        return wrapper

    def lecture_or_409():
        lec = attendance.current_lecture()
        if lec is None:
            abort(409, "No lecture is running")
        return lec

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(409)
    def json_error(e):
        return jsonify(ok=False, error=e.description), e.code

    # ------------------------------------------------------------------ student (phone)
    @app.get("/")
    def student_page():
        return render_template("student.html")

    @app.get("/api/roster/names")
    def roster_names():
        return jsonify(sorted(s.name for s in roster.all()))

    @app.post("/api/register")
    def register():
        data = request.get_json(force=True)
        student = roster.verify(data.get("name", ""), data.get("last4", ""))
        if student is None:
            return jsonify(ok=False, error="Name and last 4 digits don't match the course list"), 400
        old = current_student()
        lec = attendance.current_lecture()
        if old and old != student and lec and attendance.student_summary(lec["id"], old.student_id)["checked_in"]:
            return jsonify(ok=False, error=f"This phone already checked in {old.name} in this lecture"), 409
        resp = jsonify(ok=True, name=student.name)
        resp.set_cookie(DEVICE_COOKIE, devices.bind(student), max_age=DEVICE_COOKIE_AGE, httponly=True,
                        samesite="Lax", secure=request.headers.get("X-Forwarded-Proto") == "https")
        pending = session.pop("pending_token", None)
        if pending:  # the student arrived by scanning the rotating QR before registering
            attendance.heard(student.student_id, pending)
        return resp

    @app.get("/api/me")
    def me():
        s = current_student()
        if s is None:
            return jsonify(registered=False)
        lec = attendance.current_lecture()
        state = {"registered": True, "name": s.name, "lecture": None}
        if lec:
            pulse = attendance.active_pulse(lec["id"])
            poll = polls.open_poll(lec["id"])
            state["lecture"] = {"id": lec["id"], "title": lec["title"],
                                **attendance.student_summary(lec["id"], s.student_id),
                                "pulse_active": bool(pulse) and not attendance.heard_pulse(pulse["id"], s.student_id)}
            if poll:
                state["poll"] = {"id": poll["id"], "question": poll["question"], "options": poll["options"],
                                 "voted": polls.has_voted(poll["id"], s.student_id)}
        return jsonify(state)

    @app.post("/api/heard")
    def heard():
        s = current_student()
        if s is None:
            abort(401, "Register first")
        res = attendance.heard(s.student_id, request.get_json(force=True).get("token", ""),
                               request.cookies.get(DEVICE_COOKIE))
        return jsonify(ok=res.ok, message=res.message, kind=res.kind)

    @app.get("/j/<token>")
    def join_by_qr(token):
        """Rotating-QR fallback: the QR encodes this URL, so scanning it both opens the app and checks in."""
        s = current_student()
        if s is None:
            session["pending_token"] = token
            return redirect("/")
        res = attendance.heard(s.student_id, token, request.cookies.get(DEVICE_COOKIE))
        return redirect(f"/?qr={'ok' if res.ok else 'fail'}")

    @app.post("/api/vote")
    def vote():
        s = current_student()
        if s is None:
            abort(401, "Register first")
        d = request.get_json(force=True)
        return jsonify(ok=polls.vote(int(d["poll_id"]), s.student_id, int(d["option"])))

    @app.post("/api/comment")
    def comment():
        s = current_student()
        if s is None:
            abort(401, "Register first")
        lec = lecture_or_409()
        d = request.get_json(force=True)
        try:
            comments.add(lec["id"], s.student_id, d.get("text", ""), bool(d.get("anonymous")))
        except ValueError as e:
            abort(400, str(e))
        return jsonify(ok=True)

    # ------------------------------------------------------------------ lecturer (laptop / projector)
    @app.get("/lecturer")
    def lecturer_page():
        return render_template("lecturer.html", authed=bool(session.get("lecturer")))

    @app.post("/lecturer/login")
    def lecturer_login():
        if secrets.compare_digest(request.form.get("pin", ""), app.config["LECTURER_PIN"]):
            session["lecturer"] = True
        return redirect("/lecturer")

    @app.post("/api/l/lecture")
    @lecturer_only
    def lecture_start():
        title = request.get_json(force=True).get("title", "")
        return jsonify(ok=True, id=attendance.start_lecture(title or time.strftime("Lecture %d/%m")))

    @app.post("/api/l/lecture/end")
    @lecturer_only
    def lecture_end():
        attendance.end_lecture()
        return jsonify(ok=True)

    @app.post("/api/l/token")
    @lecturer_only
    def new_token():
        lec = lecture_or_409()
        channel = request.get_json(force=True).get("channel", "sound")
        return jsonify(token=attendance.issue_token(lec["id"], "qr" if channel == "qr" else "sound"))

    @app.post("/api/l/pulse")
    @lecturer_only
    def pulse():
        return jsonify(ok=True, id=attendance.start_pulse(lecture_or_409()["id"]))

    @app.post("/api/l/poll")
    @lecturer_only
    def poll_create():
        d = request.get_json(force=True)
        try:
            return jsonify(ok=True, id=polls.create(lecture_or_409()["id"], d.get("question", ""), d.get("options", [])))
        except ValueError as e:
            abort(400, str(e))

    @app.post("/api/l/poll/<int:poll_id>/close")
    @lecturer_only
    def poll_close(poll_id):
        polls.close(poll_id)
        return jsonify(ok=True)

    @app.post("/api/l/manual")
    @lecturer_only
    def manual():
        attendance.manual_check_in(lecture_or_409()["id"], request.get_json(force=True)["student_id"])
        return jsonify(ok=True)

    @app.post("/api/l/device-reset")
    @lecturer_only
    def device_reset():
        devices.reset(request.get_json(force=True)["student_id"])
        return jsonify(ok=True)

    @app.get("/api/l/state")
    @lecturer_only
    def lecturer_state():
        lec = attendance.current_lecture()
        state = {"lecture": None, "roster_size": len(roster.all()), "llm": llm.name}
        if lec:
            rows = []
            for s in roster.all():
                sm = attendance.student_summary(lec["id"], s.student_id)
                rows.append({"student_id": s.student_id, "name": s.name, **sm,
                             "device_flag": devices.device_count(s.student_id) > 1})
            pulse = attendance.active_pulse(lec["id"])
            state.update(
                lecture={"id": lec["id"], "title": lec["title"], "started_at": lec["started_at"]},
                rows=rows,
                pulse={"id": pulse["id"], "seconds_left": int(pulse["ends_at"] - time.time())} if pulse else None,
                poll=polls.latest(lec["id"]),
                comments=comments.for_lecture(lec["id"]),
            )
        return jsonify(state)

    @app.post("/api/l/roster")
    @lecturer_only
    def roster_upload():
        f = request.files.get("file")
        if not f:
            abort(400, "Choose a CSV file")
        try:
            n = roster.replace_all(CsvRosterSource(f.read().decode("utf-8-sig")))
        except (ValueError, UnicodeDecodeError) as e:
            abort(400, str(e))
        return jsonify(ok=True, count=n)

    @app.get("/lecturer/export.xlsx")
    @lecturer_only
    def export_xlsx():
        data = ExcelExporter(roster, attendance, devices, polls, comments).build()
        return send_file(io.BytesIO(data), as_attachment=True, download_name=f"attendance-{time.strftime('%Y-%m-%d')}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.post("/api/l/summary")
    @lecturer_only
    def summary():
        f = request.files.get("file")
        text = f.read().decode("utf-8", errors="replace") if f else request.form.get("text", "")
        try:
            return jsonify(ok=True, **summarize_lecture(text, llm))
        except ValueError as e:
            abort(400, str(e))

    @app.post("/api/l/homework")
    @lecturer_only
    def homework():
        subs = {Path(f.filename).stem: f.read().decode("utf-8", errors="replace")
                for f in request.files.getlist("files") if f.filename}
        try:
            return jsonify(ok=True, **review_homework(subs, request.form.get("assignment", ""), llm))
        except ValueError as e:
            abort(400, str(e))

    return app
