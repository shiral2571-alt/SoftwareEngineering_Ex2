"""Integration tests through the HTTP API (Flask test client) — the same calls the phone and laptop pages make."""
import pytest

from app import create_app
from app.ai_tools import OfflineClient


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "test.db"), lecturer_pin="4242", llm=OfflineClient())


@pytest.fixture
def lecturer(app):
    c = app.test_client()
    c.post("/lecturer/login", data={"pin": "4242"})
    return c


def test_lecturer_api_requires_pin(app):
    c = app.test_client()
    assert c.get("/api/l/state").status_code == 401
    c.post("/lecturer/login", data={"pin": "0000"})
    assert c.get("/api/l/state").status_code == 401


def test_full_check_in_flow(app, lecturer):
    lecturer.post("/api/l/lecture", json={"title": "SOLID"})
    phone = app.test_client()
    assert phone.get("/api/me").json == {"registered": False}
    assert phone.post("/api/register", json={"name": "Nobody Here"}).status_code == 400
    r = phone.post("/api/register", json={"name": "noa levi"})
    assert r.json["ok"] and "HttpOnly" in r.headers["Set-Cookie"]

    token = lecturer.post("/api/l/token", json={"channel": "sound"}).json["token"]
    assert phone.post("/api/heard", json={"token": token}).json["message"] == "Checked in"
    assert phone.get("/api/me").json["lecture"]["checked_in"]
    row = next(r for r in lecturer.get("/api/l/state").json["rows"] if r["name"] == "Noa Levi")
    assert row["status"] == "Present"


def test_phone_cannot_switch_student_after_check_in(app, lecturer):
    lecturer.post("/api/l/lecture", json={"title": "L"})
    phone = app.test_client()
    phone.post("/api/register", json={"name": "Noa Levi"})
    phone.post("/api/heard", json={"token": lecturer.post("/api/l/token", json={}).json["token"]})
    r = phone.post("/api/register", json={"name": "Daniel Cohen"})
    assert r.status_code == 409


def test_qr_scan_before_registering_checks_in_after_registering(app, lecturer):
    lecturer.post("/api/l/lecture", json={"title": "L"})
    token = lecturer.post("/api/l/token", json={"channel": "qr"}).json["token"]
    phone = app.test_client()
    assert phone.get(f"/j/{token}").status_code == 302
    phone.post("/api/register", json={"name": "Daniel Cohen"})
    assert phone.get("/api/me").json["lecture"]["method"] == "qr"


def test_poll_and_comment_round_trip(app, lecturer):
    lecturer.post("/api/l/lecture", json={"title": "L"})
    pid = lecturer.post("/api/l/poll", json={"question": "Clear?", "options": ["Yes", "No"]}).json["id"]
    phone = app.test_client()
    phone.post("/api/register", json={"name": "Noa Levi"})
    assert phone.get("/api/me").json["poll"]["question"] == "Clear?"
    assert phone.post("/api/vote", json={"poll_id": pid, "option": 1}).json["ok"]
    phone.post("/api/comment", json={"text": "Slower please", "anonymous": True})
    st = lecturer.get("/api/l/state").json
    assert st["poll"]["counts"] == [0, 1] and st["comments"][0]["author"] == "Anonymous"


def test_excel_download(lecturer):
    lecturer.post("/api/l/lecture", json={"title": "L"})
    r = lecturer.get("/lecturer/export.xlsx")
    assert r.status_code == 200 and r.data[:2] == b"PK"  # xlsx is a zip file


def test_second_phone_cannot_take_a_registered_name(app, lecturer):
    first, second = app.test_client(), app.test_client()
    assert first.post("/api/register", json={"name": "Noa Levi"}).json["ok"]
    r = second.post("/api/register", json={"name": "Noa Levi"})
    assert r.status_code == 409 and "another phone" in r.json["error"]
    lecturer.post("/api/l/lecture", json={"title": "L"})
    noa = next(x for x in lecturer.get("/api/l/state").json["rows"] if x["name"] == "Noa Levi")
    assert noa["registered"]
    lecturer.post("/api/l/device-reset", json={"student_id": noa["student_id"]})
    assert second.post("/api/register", json={"name": "Noa Levi"}).json["ok"]
