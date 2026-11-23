"""Web-based teaching tool — Flask application factory.

Routes are thin (routes_student.py, routes_lecturer.py): they read the request, call a service class and
return JSON/HTML. All decisions live in the service classes, which is what the unit tests exercise.
"""
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from flask import Flask, jsonify

from . import db as dbmod
from .app_settings import AppSettings
from .attendance import AttendanceService
from .forum import ForumService
from .identity import DeviceRegistry
from .lectures import LectureService, MaterialService
from .llm import LLMSettings
from .polls import PollService
from .roster import CourseRoster, CourseService, CsvRosterSource

SAMPLE_ROSTER = Path(__file__).resolve().parent.parent / "data" / "sample_roster.csv"


@dataclass
class Services:
    """Everything the routes need, created once per app (simple dependency injection)."""
    courses: CourseService
    roster: CourseRoster
    devices: DeviceRegistry
    lectures: LectureService
    attendance: AttendanceService
    polls: PollService
    forum: ForumService
    materials: MaterialService
    llm_settings: LLMSettings
    app_settings: AppSettings
    llm_override: object = None  # tests inject a fake LLM here

    def llm(self):
        return self.llm_override or self.llm_settings.client()


def create_app(db_path: str = "teaching_tool.db", lecturer_pin: str | None = None, llm=None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    app.config["LECTURER_PIN"] = lecturer_pin or os.environ.get("LECTURER_PIN") or f"{secrets.randbelow(10**6):06d}"

    conn = dbmod.connect(db_path)
    roster = CourseRoster(conn)
    svc = Services(courses=CourseService(conn), roster=roster, devices=DeviceRegistry(conn, roster),
                   lectures=LectureService(conn), attendance=AttendanceService(conn), polls=PollService(conn),
                   forum=ForumService(conn), materials=MaterialService(conn), llm_settings=LLMSettings(conn),
                   app_settings=AppSettings(conn), llm_override=llm)
    if os.environ.get("PUBLIC_URL"):  # e.g. set by the start script from the tunnel address
        svc.app_settings.set_public_url(os.environ["PUBLIC_URL"])
    if not svc.courses.all() and SAMPLE_ROSTER.exists():  # first run: a demo course with a fictional roster
        cid = svc.courses.create("Intro to Software Engineering")
        roster.import_into(cid, CsvRosterSource(SAMPLE_ROSTER.read_text(encoding="utf-8")))
    app.extensions["services"] = svc

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    def json_error(e):
        return jsonify(ok=False, error=e.description), e.code

    from . import routes_lecturer, routes_student
    routes_student.register(app, svc)
    routes_lecturer.register(app, svc)
    return app
