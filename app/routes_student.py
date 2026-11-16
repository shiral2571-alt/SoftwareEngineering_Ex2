"""Student (phone) routes."""
from flask import abort, jsonify, redirect, render_template, request, session

DEVICE_COOKIE = "device"
DEVICE_COOKIE_AGE = 365 * 24 * 3600  # server-set HttpOnly cookie: survives Safari's 7-day script-storage cap


def register(app, svc):
    def me():
        return svc.devices.student_for(request.cookies.get(DEVICE_COOKIE))

    def me_or_401():
        s = me()
        if s is None:
            abort(401, "Register first")
        return s

    def visible_lecture(lecture_id, student):
        """Students only see Open/Closed lectures of their own courses (FR-3.1)."""
        lec = svc.lectures.get(lecture_id)
        if lec is None or lec["state"] == "draft" or not svc.roster.is_enrolled(lec["course_id"], student.student_id):
            abort(404, "Lecture not found")
        return lec

    @app.get("/")
    def student_page():
        return render_template("student.html")

    @app.get("/api/roster/names")
    def roster_names():
        return jsonify(svc.roster.all_names())

    @app.post("/api/register")
    def register_phone():
        student = svc.roster.find_by_name(request.get_json(force=True).get("name", ""))
        if student is None:
            return jsonify(ok=False, error="Choose your name from the list"), 400
        old = me()
        if old and old != student:  # FR-4.9: no switching names after checking someone in during an open lecture
            for lec in svc.lectures.visible_to_student(svc.roster.courses_of(old.student_id)):
                if lec["state"] == "open" and svc.attendance.status_of(lec["id"], old.student_id) == "present":
                    return jsonify(ok=False, error=f"This phone already checked in {old.name} in this lecture"), 409
        claim = svc.devices.claim(student, request.cookies.get(DEVICE_COOKIE))
        if not claim.ok:
            return jsonify(ok=False, error=claim.error), 409
        resp = jsonify(ok=True, name=student.name)
        resp.set_cookie(DEVICE_COOKIE, claim.device_token, max_age=DEVICE_COOKIE_AGE, httponly=True,
                        samesite="Lax", secure=request.headers.get("X-Forwarded-Proto") == "https")
        pending = session.pop("pending_token", None)
        if pending:  # arrived by scanning the QR before registering
            svc.attendance.heard(student.student_id, pending)
        return resp

    @app.get("/api/me")
    def my_home():
        s = me()
        if s is None:
            return jsonify(registered=False)
        lectures = []
        for lec in svc.lectures.visible_to_student(svc.roster.courses_of(s.student_id)):
            window = svc.attendance.open_window_of(lec["id"]) if lec["state"] == "open" else None
            lectures.append({"id": lec["id"], "title": lec["title"], "course": lec["course"], "state": lec["state"],
                             "status": svc.attendance.status_of(lec["id"], s.student_id),
                             "checkin": window["channel"] if window else None})
        return jsonify(registered=True, name=s.name, lectures=lectures)

    @app.get("/api/lecture/<int:lecture_id>")
    def my_lecture(lecture_id):
        s = me_or_401()
        lec = visible_lecture(lecture_id, s)
        window = svc.attendance.open_window_of(lecture_id) if lec["state"] == "open" else None
        return jsonify(
            id=lec["id"], title=lec["title"], state=lec["state"],
            status=svc.attendance.status_of(lecture_id, s.student_id),
            checkin=window["channel"] if window else None,
            polls=svc.polls.for_student(lecture_id, s.student_id),
            forum=svc.forum.of_lecture(lecture_id, viewer_id=s.student_id),
            materials=[{"id": m["id"], "title": m["title"], "content": m["content"]}
                       for m in svc.materials.of_lecture(lecture_id, students_only=True)])

    @app.post("/api/heard")
    def heard():
        s = me_or_401()
        res = svc.attendance.heard(s.student_id, request.get_json(force=True).get("token", ""))
        return jsonify(ok=res.ok, message=res.message)

    @app.get("/j/<token>")
    def join_by_qr(token):
        """The rotating QR encodes this URL: scanning it opens the app and checks in (FR-4.6)."""
        s = me()
        if s is None:
            session["pending_token"] = token
            return redirect("/")
        res = svc.attendance.heard(s.student_id, token)
        return redirect(f"/?qr={'ok' if res.ok else 'fail'}")

    @app.post("/api/answer")
    def answer():
        s = me_or_401()
        d = request.get_json(force=True)
        opt = d.get("option")
        ok = svc.polls.answer(int(d["question_id"]), s.student_id,
                              int(opt) if opt is not None else None, d.get("text"))
        return jsonify(ok=ok)

    @app.post("/api/lecture/<int:lecture_id>/post")
    def post(lecture_id):
        s = me_or_401()
        visible_lecture(lecture_id, s)
        d = request.get_json(force=True)
        try:
            svc.forum.post(lecture_id, s.student_id, d.get("text", ""), bool(d.get("anonymous")))
        except ValueError as e:
            abort(400, str(e))
        return jsonify(ok=True)

    @app.post("/api/post/<int:post_id>/upvote")
    def upvote(post_id):
        s = me_or_401()
        return jsonify(ok=True, upvoted=svc.forum.toggle_upvote(post_id, s.student_id))
