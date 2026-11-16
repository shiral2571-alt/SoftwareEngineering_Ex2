"""Integration tests through the HTTP API (Flask test client) — the same calls the phone and laptop pages make."""
import pytest

from app import create_app
from app.llm import OfflineClient


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "test.db"), lecturer_pin="4242", llm=OfflineClient())


@pytest.fixture
def lecturer(app):
    c = app.test_client()
    c.post("/lecturer/login", data={"pin": "4242"})
    return c


def course_id(lecturer):
    return lecturer.get("/api/l/courses").json[0]["id"]  # the sample course created on first run


def new_open_lecture(lecturer, title="L"):
    lid = lecturer.post(f"/api/l/courses/{course_id(lecturer)}/lectures", json={"title": title}).json["id"]
    lecturer.post(f"/api/l/lectures/{lid}/state", json={"action": "open"})
    return lid


def phone(app, name):
    c = app.test_client()
    assert c.post("/api/register", json={"name": name}).json["ok"]
    return c


def test_lecturer_api_requires_pin(app):
    c = app.test_client()
    assert c.get("/api/l/courses").status_code == 401
    c.post("/lecturer/login", data={"pin": "0000"})
    assert c.get("/api/l/courses").status_code == 401


def test_full_sound_check_in_flow(app, lecturer):
    lid = new_open_lecture(lecturer, "SOLID")
    p = app.test_client()
    assert p.get("/api/me").json == {"registered": False}
    assert p.post("/api/register", json={"name": "Nobody Here"}).status_code == 400
    r = p.post("/api/register", json={"name": "noa levi"})
    assert r.json["ok"] and "HttpOnly" in r.headers["Set-Cookie"]

    assert lecturer.post(f"/api/l/lectures/{lid}/token", json={}).status_code == 409  # no window yet
    lecturer.post(f"/api/l/lectures/{lid}/checkin", json={"action": "start", "channel": "sound"})
    assert p.get(f"/api/lecture/{lid}").json["checkin"] == "sound"
    token = lecturer.post(f"/api/l/lectures/{lid}/token", json={}).json["token"]
    assert p.post("/api/heard", json={"token": token}).json["message"] == "Checked in"
    row = next(r for r in lecturer.get(f"/api/l/lectures/{lid}").json["rows"] if r["name"] == "Noa Levi")
    assert row["status"] == "present" and row["registered"]


def test_drafts_are_hidden_from_students(app, lecturer):
    lid = lecturer.post(f"/api/l/courses/{course_id(lecturer)}/lectures", json={"title": "Secret"}).json["id"]
    p = phone(app, "Noa Levi")
    assert p.get("/api/me").json["lectures"] == []
    assert p.get(f"/api/lecture/{lid}").status_code == 404
    lecturer.post(f"/api/l/lectures/{lid}/state", json={"action": "open"})
    assert [l["id"] for l in p.get("/api/me").json["lectures"]] == [lid]


def test_lifecycle_errors_are_reported(app, lecturer):
    lid = lecturer.post(f"/api/l/courses/{course_id(lecturer)}/lectures", json={"title": "X"}).json["id"]
    assert lecturer.post(f"/api/l/lectures/{lid}/state", json={"action": "close"}).status_code == 409


def test_second_phone_cannot_take_a_registered_name(app, lecturer):
    first = phone(app, "Noa Levi")
    second = app.test_client()
    r = second.post("/api/register", json={"name": "Noa Levi"})
    assert r.status_code == 409 and "another phone" in r.json["error"]
    lid = new_open_lecture(lecturer)
    noa = next(x for x in lecturer.get(f"/api/l/lectures/{lid}").json["rows"] if x["name"] == "Noa Levi")
    lecturer.post("/api/l/devices/reset", json={"student_id": noa["student_id"]})
    assert second.post("/api/register", json={"name": "Noa Levi"}).json["ok"]


def test_phone_cannot_switch_student_after_check_in(app, lecturer):
    lid = new_open_lecture(lecturer)
    p = phone(app, "Noa Levi")
    lecturer.post(f"/api/l/lectures/{lid}/checkin", json={"action": "start", "channel": "sound"})
    p.post("/api/heard", json={"token": lecturer.post(f"/api/l/lectures/{lid}/token", json={}).json["token"]})
    assert p.post("/api/register", json={"name": "Daniel Cohen"}).status_code == 409


def test_qr_scan_before_registering(app, lecturer):
    lid = new_open_lecture(lecturer)
    lecturer.post(f"/api/l/lectures/{lid}/checkin", json={"action": "start", "channel": "qr"})
    token = lecturer.post(f"/api/l/lectures/{lid}/token", json={}).json["token"]
    p = app.test_client()
    assert p.get(f"/j/{token}").status_code == 302
    p.post("/api/register", json={"name": "Daniel Cohen"})
    assert p.get(f"/api/lecture/{lid}").json["status"] == "present"


def test_manual_late_status(app, lecturer):
    lid = new_open_lecture(lecturer)
    sid = lecturer.get(f"/api/l/lectures/{lid}").json["rows"][0]["student_id"]
    assert lecturer.post(f"/api/l/lectures/{lid}/status", json={"student_id": sid, "status": "late"}).json["ok"]
    assert lecturer.post(f"/api/l/lectures/{lid}/status", json={"student_id": sid, "status": "x"}).status_code == 400


def test_poll_prepared_in_draft_then_answered(app, lecturer):
    lid = lecturer.post(f"/api/l/courses/{course_id(lecturer)}/lectures", json={"title": "L"}).json["id"]
    pid = lecturer.post(f"/api/l/lectures/{lid}/polls", json={
        "title": "Check", "show_correct": True,
        "questions": [{"text": "2+2?", "kind": "quiz", "options": ["3", "4"], "correct": 1},
                      {"text": "Comments?", "kind": "text"}]}).json["id"]
    lecturer.post(f"/api/l/lectures/{lid}/state", json={"action": "open"})
    p = phone(app, "Noa Levi")
    assert p.get(f"/api/lecture/{lid}").json["polls"] == []          # not launched yet
    lecturer.post(f"/api/l/polls/{pid}", json={"action": "launch"})
    qs = p.get(f"/api/lecture/{lid}").json["polls"][0]["questions"]
    assert p.post("/api/answer", json={"question_id": qs[0]["id"], "option": 1}).json["ok"]
    assert p.post("/api/answer", json={"question_id": qs[1]["id"], "text": "More examples"}).json["ok"]
    assert p.get(f"/api/lecture/{lid}").json["polls"][0]["questions"][0]["correct"] == 1
    result = lecturer.get(f"/api/l/lectures/{lid}").json["polls"][0]["questions"]
    assert result[0]["percent_correct"] == 100 and result[1]["texts"] == ["More examples"]


def test_absent_student_can_still_participate(app, lecturer):
    lid = new_open_lecture(lecturer)
    p = phone(app, "Daniel Cohen")  # never checked in (e.g. watching from home)
    assert p.post(f"/api/lecture/{lid}/post", json={"text": "Question from home", "anonymous": False}).json["ok"]
    assert p.get(f"/api/lecture/{lid}").json["status"] == "absent"


def test_forum_round_trip(app, lecturer):
    lid = new_open_lecture(lecturer)
    p = phone(app, "Noa Levi")
    p.post(f"/api/lecture/{lid}/post", json={"text": "Slower please", "anonymous": True})
    post = lecturer.get(f"/api/l/lectures/{lid}").json["forum"][0]
    assert post["author"] == "Anonymous"
    lecturer.post(f"/api/l/posts/{post['id']}/reply", json={"text": "Sure!"})
    assert p.post(f"/api/post/{post['id']}/upvote").json["upvoted"]
    seen = p.get(f"/api/lecture/{lid}").json["forum"][0]
    assert seen["replies"][0]["text"] == "Sure!" and seen["votes"] == 1


def test_settings_never_expose_the_key(lecturer):
    r = lecturer.post("/api/l/settings", json={"provider": "google", "model": "gemini-3.5-flash-lite",
                                              "api_key": "AIza-very-secret-key-9876"})
    assert r.json["ok"] and "secret" not in r.get_data(as_text=True)
    assert "secret" not in lecturer.get("/api/l/settings").get_data(as_text=True)


def test_feedback_is_saved_as_private_material(app, lecturer):
    lid = new_open_lecture(lecturer)
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:20.000\nUm today we learn about interfaces and classes.\n"
    r = lecturer.post(f"/api/l/lectures/{lid}/feedback", data={"text": vtt})
    assert r.json["ok"]
    assert lecturer.get(f"/api/l/lectures/{lid}").json["materials"][0]["visible_to_students"] == 0
    assert phone(app, "Noa Levi").get(f"/api/lecture/{lid}").json["materials"] == []


def test_excel_download(lecturer):
    new_open_lecture(lecturer)
    r = lecturer.get(f"/api/l/courses/{course_id(lecturer)}/export.xlsx")
    assert r.status_code == 200 and r.data[:2] == b"PK"  # xlsx is a zip file
