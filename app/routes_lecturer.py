"""Lecturer (laptop / projector) routes. Everything here requires the PIN (FR-1.1)."""
import io
import secrets
import time
from functools import wraps
from pathlib import Path

from flask import Response, abort, jsonify, redirect, render_template, request, send_file, session

from .ai_tools import student_summary, teaching_feedback
from .export import ExcelExporter
from .lectures import LectureStateError
from .llm import LLMError, test_connection
from .polls import Question, parse_poll_file, template_csv
from .roster import roster_source_for
from .textfiles import extract_text


def register(app, svc):
    def lecturer_only(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if not session.get("lecturer"):
                abort(401, "Lecturer login required")
            return f(*a, **kw)
        return wrapper

    def lecture_or_404(lecture_id):
        lec = svc.lectures.get(lecture_id)
        if lec is None:
            abort(404, "Lecture not found")
        return lec

    def body():
        return request.get_json(force=True, silent=True) or {}

    def uploaded_text():
        f = request.files.get("file")
        return f.read().decode("utf-8", errors="replace") if f else request.form.get("text", "")

    # ------------------------------------------------------------------ pages & login
    @app.get("/lecturer")
    def lecturer_page():
        return render_template("lecturer.html", authed=bool(session.get("lecturer")))

    @app.post("/lecturer/login")
    def lecturer_login():
        if secrets.compare_digest(request.form.get("pin", ""), app.config["LECTURER_PIN"]):
            session["lecturer"] = True
        return redirect("/lecturer")

    @app.post("/lecturer/logout")
    def lecturer_logout():
        session.pop("lecturer", None)
        return redirect("/lecturer")

    # ------------------------------------------------------------------ courses
    @app.get("/api/l/courses")
    @lecturer_only
    def courses():
        return jsonify(svc.courses.all())

    @app.post("/api/l/courses")
    @lecturer_only
    def course_create():
        try:
            return jsonify(ok=True, id=svc.courses.create(body().get("name", "")))
        except ValueError as e:
            abort(400, str(e))

    @app.post("/api/l/courses/<int:course_id>/roster")
    @lecturer_only
    def roster_upload(course_id):
        f = request.files.get("file")
        if not f or svc.courses.get(course_id) is None:
            abort(400, "Choose a CSV or Excel file")
        try:
            n = svc.roster.import_into(course_id, roster_source_for(f.filename, f.read()))
        except (ValueError, UnicodeDecodeError) as e:
            abort(400, str(e))
        return jsonify(ok=True, count=n)

    @app.get("/api/l/courses/<int:course_id>/lectures")
    @lecturer_only
    def course_lectures(course_id):
        return jsonify(svc.lectures.of_course(course_id))

    @app.post("/api/l/courses/<int:course_id>/lectures")
    @lecturer_only
    def lecture_create(course_id):
        try:
            return jsonify(ok=True, id=svc.lectures.create(course_id, body().get("title", "")))
        except ValueError as e:
            abort(400, str(e))

    @app.get("/api/l/courses/<int:course_id>/export.xlsx")
    @lecturer_only
    def export_xlsx(course_id):
        course = svc.courses.get(course_id) or abort(404, "Course not found")
        data = ExcelExporter(svc.courses, svc.roster, svc.lectures, svc.attendance, svc.polls, svc.forum).build(course_id)
        return send_file(io.BytesIO(data), as_attachment=True,
                         download_name=f"{course['name']} - attendance {time.strftime('%Y-%m-%d')}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ------------------------------------------------------------------ one lecture
    @app.get("/api/l/lectures/<int:lecture_id>")
    @lecturer_only
    def lecture_state(lecture_id):
        lec = lecture_or_404(lecture_id)
        students = svc.roster.students_of(lec["course_id"])
        rows = svc.attendance.sheet(lecture_id, students)
        for r in rows:
            r["registered"] = svc.devices.is_registered(r["student_id"])
        return jsonify(lecture=lec, checkin=svc.attendance.open_window_of(lecture_id), rows=rows,
                       polls=svc.polls.of_lecture(lecture_id), forum=svc.forum.of_lecture(lecture_id),
                       materials=svc.materials.of_lecture(lecture_id), llm=svc.llm().name)

    @app.post("/api/l/lectures/<int:lecture_id>/state")
    @lecturer_only
    def lecture_transition(lecture_id):
        lecture_or_404(lecture_id)
        action = body().get("action")
        try:
            {"open": svc.lectures.open, "close": svc.lectures.close, "reopen": svc.lectures.reopen}[action](lecture_id)
        except KeyError:
            abort(400, "Unknown action")
        except LectureStateError as e:
            abort(409, str(e))
        return jsonify(ok=True)

    @app.post("/api/l/lectures/<int:lecture_id>/rename")
    @lecturer_only
    def lecture_rename(lecture_id):
        svc.lectures.rename(lecture_id, body().get("title", ""))
        return jsonify(ok=True)

    # ------------------------------------------------------------------ attendance
    @app.post("/api/l/lectures/<int:lecture_id>/checkin")
    @lecturer_only
    def checkin(lecture_id):
        d = body()
        try:
            if d.get("action") == "start":
                svc.attendance.open_window(lecture_id, d.get("channel", "sound"))
            else:
                svc.attendance.close_window(lecture_id)
        except ValueError as e:
            abort(409, str(e))
        return jsonify(ok=True)

    @app.post("/api/l/lectures/<int:lecture_id>/token")
    @lecturer_only
    def token(lecture_id):
        try:
            return jsonify(token=svc.attendance.issue_token(lecture_id))
        except ValueError as e:
            abort(409, str(e))

    @app.post("/api/l/lectures/<int:lecture_id>/status")
    @lecturer_only
    def set_status(lecture_id):
        d = body()
        try:
            svc.attendance.set_status(lecture_id, d["student_id"], d["status"])
        except (KeyError, ValueError) as e:
            abort(400, str(e))
        return jsonify(ok=True)

    @app.post("/api/l/devices/reset")
    @lecturer_only
    def device_reset():
        svc.devices.reset(body().get("student_id", ""))
        return jsonify(ok=True)

    # ------------------------------------------------------------------ polls
    @app.post("/api/l/lectures/<int:lecture_id>/polls")
    @lecturer_only
    def poll_create(lecture_id):
        lecture_or_404(lecture_id)
        d = body()
        try:
            qs = [Question(q.get("text", ""), q.get("kind", "choice"), q.get("options", []), q.get("correct"))
                  for q in d.get("questions", [])]
            return jsonify(ok=True, id=svc.polls.create(lecture_id, d.get("title", ""), qs, bool(d.get("show_correct"))))
        except ValueError as e:
            abort(400, str(e))

    @app.post("/api/l/lectures/<int:lecture_id>/polls/import")
    @lecturer_only
    def poll_import(lecture_id):
        lecture_or_404(lecture_id)
        f = request.files.get("file")
        if not f:
            abort(400, "Choose an xlsx or csv file")
        try:
            qs = parse_poll_file(f.filename, f.read())
            title = request.form.get("title") or Path(f.filename).stem
            pid = svc.polls.create(lecture_id, title, qs, request.form.get("show_correct") == "true")
        except (ValueError, UnicodeDecodeError) as e:
            abort(400, str(e))
        return jsonify(ok=True, id=pid, count=len(qs))

    @app.get("/api/l/polls/template.csv")
    @lecturer_only
    def poll_template():
        return Response("﻿" + template_csv(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=poll-template.csv"})

    @app.post("/api/l/polls/<int:poll_id>")
    @lecturer_only
    def poll_action(poll_id):
        d = body()
        action = d.get("action")
        if action == "launch":
            svc.polls.launch(poll_id)
        elif action == "close":
            svc.polls.close(poll_id)
        elif action == "delete":
            svc.polls.delete(poll_id)
        elif action == "show_correct":
            svc.polls.set_show_correct(poll_id, bool(d.get("value")))
        else:
            abort(400, "Unknown action")
        return jsonify(ok=True)

    # ------------------------------------------------------------------ forum
    @app.post("/api/l/posts/<int:post_id>/reply")
    @lecturer_only
    def forum_reply(post_id):
        try:
            svc.forum.reply(post_id, body().get("text", ""))
        except ValueError as e:
            abort(400, str(e))
        return jsonify(ok=True)

    @app.post("/api/l/posts/<int:post_id>/delete")
    @lecturer_only
    def forum_delete(post_id):
        svc.forum.delete_post(post_id)
        return jsonify(ok=True)

    @app.post("/api/l/replies/<int:reply_id>/delete")
    @lecturer_only
    def forum_delete_reply(reply_id):
        svc.forum.delete_reply(reply_id)
        return jsonify(ok=True)

    # ------------------------------------------------------------------ materials & AI
    @app.post("/api/l/lectures/<int:lecture_id>/materials")
    @lecturer_only
    def material_add(lecture_id):
        lecture_or_404(lecture_id)
        f = request.files.get("file")
        title = request.form.get("title") or (f.filename if f else "Note")
        text = uploaded_text()
        if not text.strip():
            abort(400, "The file or note is empty")
        svc.materials.add(lecture_id, "file", title, text, request.form.get("visible") == "true")
        return jsonify(ok=True)

    @app.post("/api/l/materials/<int:material_id>/delete")
    @lecturer_only
    def material_delete(material_id):
        svc.materials.delete(material_id)
        return jsonify(ok=True)

    @app.post("/api/l/lectures/<int:lecture_id>/feedback")
    @lecturer_only
    def feedback(lecture_id):
        lecture_or_404(lecture_id)
        try:
            out = teaching_feedback(uploaded_text(), svc.llm())
        except ValueError as e:
            abort(400, str(e))
        svc.materials.add(lecture_id, "report", "Teaching feedback (lecturer only)", out["report"], visible=False)
        return jsonify(ok=True, **out)

    @app.post("/api/l/lectures/<int:lecture_id>/summary")
    @lecturer_only
    def summary(lecture_id):
        lecture_or_404(lecture_id)
        try:
            out = student_summary(uploaded_text(), svc.llm())
        except ValueError as e:
            abort(400, str(e))
        svc.materials.add(lecture_id, "report", "Lecture summary", out["report"],
                          visible=request.form.get("visible") == "true")
        return jsonify(ok=True, **out)

    # ------------------------------------------------------------------ assignments (feature 5, FR-7.16–7.21)
    @app.get("/api/l/courses/<int:course_id>/assignments")
    @lecturer_only
    def assignments_list(course_id):
        return jsonify(svc.assignments.of_course(course_id))

    @app.post("/api/l/courses/<int:course_id>/assignments")
    @lecturer_only
    def assignment_create(course_id):
        if svc.courses.get(course_id) is None:
            abort(404, "Course not found")
        f = request.files.get("file")
        try:
            instructions = extract_text(f.filename, f.read()) if f and f.filename else request.form.get("text", "")
            deadline = float(request.form["deadline"]) if request.form.get("deadline") else None
            aid = svc.assignments.create(course_id, request.form.get("title", ""), instructions, deadline)
        except ValueError as e:
            abort(400, str(e))
        return jsonify(ok=True, id=aid)

    @app.get("/api/l/assignments/<int:assignment_id>")
    @lecturer_only
    def assignment_detail(assignment_id):
        a = svc.assignments.get(assignment_id) or abort(404, "Assignment not found")
        return jsonify(assignment=a, submissions=svc.assignments.submissions(assignment_id))

    @app.post("/api/l/assignments/<int:assignment_id>/delete")
    @lecturer_only
    def assignment_delete(assignment_id):
        svc.assignments.delete(assignment_id)
        return jsonify(ok=True)

    # ------------------------------------------------------------------ public address for phones (FR-4.6a)
    @app.get("/api/l/public-url")
    @lecturer_only
    def public_url_get():
        return jsonify(public_url=svc.app_settings.public_url())

    @app.post("/api/l/public-url")
    @lecturer_only
    def public_url_set():
        try:
            return jsonify(ok=True, public_url=svc.app_settings.set_public_url(body().get("public_url", "")))
        except ValueError as e:
            abort(400, str(e))

    # ------------------------------------------------------------------ AI settings (FR-7.1–7.3)
    @app.get("/api/l/settings")
    @lecturer_only
    def settings_get():
        return jsonify(svc.llm_settings.public_view())

    @app.post("/api/l/settings")
    @lecturer_only
    def settings_save():
        d = body()
        try:
            svc.llm_settings.save(d.get("provider", ""), d.get("model", ""), d.get("api_key") or None)
        except ValueError as e:
            abort(400, str(e))
        return jsonify(ok=True, **svc.llm_settings.public_view())

    @app.post("/api/l/settings/clear-key")
    @lecturer_only
    def settings_clear():
        svc.llm_settings.clear_key()
        return jsonify(ok=True)

    @app.post("/api/l/settings/test")
    @lecturer_only
    def settings_test():
        try:
            reply = test_connection(svc.llm_settings.client())
        except ImportError as e:
            return jsonify(ok=False, error=f"Missing Python package: {e.name}. Run: py -m pip install -r requirements.txt")
        except (LLMError, Exception) as e:  # bad key, unknown model, no internet — report, don't crash
            return jsonify(ok=False, error=f"{e.__class__.__name__}: {str(e)[:300]}")
        return jsonify(ok=True, reply=reply[:100])
