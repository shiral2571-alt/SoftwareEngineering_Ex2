"""Unit tests for the service classes (no browser, no sound — the sound layer only delivers a token string).

Each test name maps to an SRS requirement where possible, so the testing strategy can trace coverage.
"""
import io

import pytest

from app import db as dbmod
from app.ai_tools import (extractive_summary, parse_transcript, review_homework, similarity_matrix, speaking_stats,
                          student_summary, teaching_feedback)
from app.attendance import TOKEN_ALPHABET, TOKEN_LENGTH, TOKEN_TTL, AttendanceService
from app.export import ExcelExporter
from app.forum import ForumService
from app.identity import DeviceRegistry
from app.lectures import LectureService, LectureStateError, MaterialService
from app.llm import ClaudeClient, LLMSettings, OfflineClient
from app.polls import PollService, Question, parse_poll_file, template_csv
from app.roster import CourseRoster, CourseService, CsvRosterSource, Student, key_for_name, roster_source_for

ROSTER_CSV = "name\nNoa Levi\nDaniel Cohen\n"  # like the real list: names only
NOA, DAN = key_for_name("Noa Levi"), key_for_name("Daniel Cohen")


class FakeClock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture
def env():
    conn = dbmod.connect(":memory:")
    clock = FakeClock()
    roster = CourseRoster(conn)
    courses = CourseService(conn, clock)
    cid = courses.create("SE")
    roster.import_into(cid, CsvRosterSource(ROSTER_CSV))
    lectures = LectureService(conn, clock)
    return dict(conn=conn, clock=clock, cid=cid, roster=roster, courses=courses, lectures=lectures,
                devices=DeviceRegistry(conn, roster, clock), att=AttendanceService(conn, clock),
                polls=PollService(conn, clock), forum=ForumService(conn, clock), materials=MaterialService(conn, clock))


def open_lecture(env, title="L1"):
    lid = env["lectures"].create(env["cid"], title)
    env["lectures"].open(lid)
    return lid


# ---------------- FR-2: roster ----------------
def test_names_only_csv_gets_stable_keys():
    students = CsvRosterSource("﻿Name\nNoa  Levi\n\n").load()
    assert [s.name for s in students] == ["Noa Levi"]
    assert students[0].student_id == key_for_name("noa levi")  # FR-2.3: same key on re-import


def test_csv_first_last_and_optional_id():
    assert CsvRosterSource("First Name,Last Name\nNoa,Levi\n").load()[0].name == "Noa Levi"
    assert CsvRosterSource("ID,Full Name\n1234,A B\n").load() == [Student("1234", "A B")]


def test_xlsx_roster():
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["שם פרטי", "שם משפחה"])
    wb.active.append(["נועה", "לוי"])
    buf = io.BytesIO()
    wb.save(buf)
    assert roster_source_for("list.xlsx", buf.getvalue()).load()[0].name == "נועה לוי"


def test_roster_rejects_missing_name_column_and_duplicates():
    with pytest.raises(ValueError):
        CsvRosterSource("id,email\n1,a@b.c\n").load()
    with pytest.raises(ValueError):
        CsvRosterSource("name\nNoa Levi\nnoa levi\n").load()


def test_courses_have_separate_rosters(env):
    other = env["courses"].create("Algorithms")
    env["roster"].import_into(other, CsvRosterSource("name\nNoa Levi\nItai Golan\n"))
    assert [s.name for s in env["roster"].students_of(other)] == ["Itai Golan", "Noa Levi"]
    assert env["roster"].courses_of(NOA) == [env["cid"], other]  # same person in two courses
    assert not env["roster"].is_enrolled(env["cid"], key_for_name("Itai Golan"))


# ---------------- FR-4.1/4.2: identity ----------------
def test_first_phone_owns_the_name(env):
    d, noa = env["devices"], env["roster"].find_by_name("  noa   LEVI ")
    first = d.claim(noa)
    assert first.ok and d.student_for(first.device_token) == noa
    assert d.claim(noa, first.device_token).device_token == first.device_token
    assert not d.claim(noa, "other-phone").ok
    d.reset(noa.student_id)
    assert d.student_for(first.device_token) is None and d.claim(noa, "real-noa-phone").ok


def test_switching_name_releases_the_old_one(env):
    d, r = env["devices"], env["roster"]
    tok = d.claim(r.get(NOA)).device_token
    d.claim(r.get(DAN), tok)
    assert not d.is_registered(NOA) and d.claim(r.get(NOA)).ok


# ---------------- FR-3: lecture lifecycle ----------------
def test_lecture_lifecycle_and_reopen(env):
    lec = env["lectures"]
    lid = lec.create(env["cid"], "Intro")
    assert lec.get(lid)["state"] == "draft"
    with pytest.raises(LectureStateError):
        lec.close(lid)                      # a draft cannot be closed
    lec.open(lid)
    lec.close(lid)
    lec.reopen(lid)                         # FR-3.3: closed by mistake
    assert lec.get(lid)["state"] == "open"


def test_students_never_see_drafts(env):
    lec = env["lectures"]
    draft = lec.create(env["cid"], "Draft")
    opened = open_lecture(env, "Open")
    ids = [l["id"] for l in lec.visible_to_student([env["cid"]])]
    assert opened in ids and draft not in ids


def test_closing_ends_the_checkin_window(env):
    lid = open_lecture(env)
    env["att"].open_window(lid, "sound")
    env["lectures"].close(lid)
    assert env["att"].open_window_of(lid) is None


# ---------------- FR-4: attendance ----------------
def test_tokens_only_while_a_window_is_open(env):
    lid = open_lecture(env)
    with pytest.raises(ValueError):
        env["att"].issue_token(lid)
    env["att"].open_window(lid, "sound")
    tok = env["att"].issue_token(lid)
    assert len(tok) == TOKEN_LENGTH and set(tok) <= set(TOKEN_ALPHABET)


def test_window_needs_an_open_lecture(env):
    draft = env["lectures"].create(env["cid"], "Draft")
    with pytest.raises(ValueError):
        env["att"].open_window(draft, "sound")


def test_valid_token_checks_in_once(env):
    att, lid = env["att"], open_lecture(env)
    att.open_window(lid, "sound")
    tok = att.issue_token(lid)
    assert att.heard(NOA, tok).message == "Checked in"
    assert att.heard(NOA, tok).message == "Already checked in"
    assert att.record_of(lid, NOA)["method"] == "sound"


def test_expired_token_is_rejected(env):
    att, lid = env["att"], open_lecture(env)
    att.open_window(lid, "sound")
    tok = att.issue_token(lid)
    env["clock"].advance(TOKEN_TTL["sound"] + 1)  # a recording replayed to a friend later
    assert not att.heard(NOA, tok).ok and att.status_of(lid, NOA) == "absent"


def test_token_after_the_lecturer_ended_checkin_is_rejected(env):
    att, lid = env["att"], open_lecture(env)
    att.open_window(lid, "qr")
    tok = att.issue_token(lid)
    att.close_window(lid)  # D-14: whoever missed it is late
    res = att.heard(NOA, tok)
    assert not res.ok and "ended" in res.message


def test_student_from_another_course_cannot_check_in(env):
    other = env["courses"].create("Other")
    env["roster"].import_into(other, CsvRosterSource("name\nItai Golan\n"))
    att, lid = env["att"], open_lecture(env)
    att.open_window(lid, "sound")
    assert not att.heard(key_for_name("Itai Golan"), att.issue_token(lid)).ok


def test_unknown_token_and_lowercase(env):
    att, lid = env["att"], open_lecture(env)
    att.open_window(lid, "qr")
    assert not att.heard(NOA, "ZZZZZZ").ok
    assert att.heard(NOA, att.issue_token(lid).lower()).ok
    assert att.record_of(lid, NOA)["method"] == "qr"


def test_lecturer_sets_late_and_can_edit_after_close(env):
    att, lid = env["att"], open_lecture(env)
    env["lectures"].close(lid)
    att.set_status(lid, DAN, "late")          # FR-4.8: manual, also after the lecture is closed
    assert att.record_of(lid, DAN) == {"status": "late", "method": "manual", "at": env["clock"]()}
    with pytest.raises(ValueError):
        att.set_status(lid, DAN, "sleeping")


def test_attendance_sheet_defaults_to_absent(env):
    lid = open_lecture(env)
    sheet = env["att"].sheet(lid, env["roster"].students_of(env["cid"]))
    assert {r["name"]: r["status"] for r in sheet} == {"Daniel Cohen": "absent", "Noa Levi": "absent"}


# ---------------- FR-5: polls ----------------
def quiz(text="2+2?", correct=1):
    return Question(text, "quiz", ["3", "4", "5"], correct)


def test_poll_with_several_question_kinds(env):
    p, lid = env["polls"], open_lecture(env)
    pid = p.create(lid, "Check", [quiz(), Question("Clear?", "choice", ["Yes", "No"]),
                                  Question("What to repeat?", "text")])
    p.launch(pid)
    q_quiz, q_choice, q_text = [q["id"] for q in p.of_lecture(lid)[0]["questions"]]
    assert p.answer(q_quiz, NOA, 1) and p.answer(q_quiz, DAN, 0)
    assert not p.answer(q_quiz, NOA, 2)        # one answer per student
    assert p.answer(q_text, NOA, text="Liskov please")
    assert not p.answer(q_choice, NOA, 7)      # no such option
    res = p.of_lecture(lid)[0]["questions"]
    assert res[0]["percent_correct"] == 50 and res[2]["texts"] == ["Liskov please"]


def test_quiz_validation():
    with pytest.raises(ValueError):
        Question("No answer marked", "quiz", ["a", "b"]).validate()
    with pytest.raises(ValueError):
        Question("One option", "choice", ["a"]).validate()
    assert Question("Free", "text", ["ignored"]).validate().options == []


def test_draft_and_closed_polls_cannot_be_answered(env):
    p, lid = env["polls"], open_lecture(env)
    pid = p.create(lid, "Later", [quiz()])
    qid = p.of_lecture(lid)[0]["questions"][0]["id"]
    assert not p.answer(qid, NOA, 1)           # prepared in advance, not launched yet
    p.launch(pid)
    p.close(pid)
    assert not p.answer(qid, NOA, 1)


def test_correct_answer_shown_only_if_allowed_and_answered(env):
    p, lid = env["polls"], open_lecture(env)
    pid = p.create(lid, "Q", [quiz()], show_correct=True)
    p.launch(pid)
    qid = p.of_lecture(lid)[0]["questions"][0]["id"]
    assert "correct" not in p.for_student(lid, NOA)[0]["questions"][0]
    p.answer(qid, NOA, 0)
    assert p.for_student(lid, NOA)[0]["questions"][0]["correct"] == 1
    p.set_show_correct(pid, False)
    assert "correct" not in p.for_student(lid, NOA)[0]["questions"][0]


def test_poll_import_template_round_trip():
    qs = parse_poll_file("poll.csv", template_csv().encode("utf-8"))
    assert [q.kind for q in qs] == ["quiz", "choice", "text"] and qs[0].correct == 1


def test_poll_import_reports_the_bad_row():
    data = "question,type,option1,option2,correct\nOk?,choice,a,b,\nBad quiz,quiz,a,b,\n".encode()
    with pytest.raises(ValueError, match="Row 3"):
        parse_poll_file("p.csv", data)


# ---------------- FR-6: forum ----------------
def test_forum_anonymous_is_fully_anonymous(env):
    f, lid = env["forum"], open_lecture(env)
    pid = f.post(lid, NOA, "Slower please", anonymous=True)
    row = env["conn"].execute("SELECT student_id FROM posts WHERE id = ?", (pid,)).fetchone()
    assert row["student_id"] is None                     # D-8: not stored at all
    assert f.of_lecture(lid)[0]["author"] == "Anonymous"


def test_forum_reply_upvote_order_and_delete(env):
    f, lid = env["forum"], open_lecture(env)
    a = f.post(lid, NOA, "First", anonymous=False)
    b = f.post(lid, DAN, "Popular", anonymous=False)
    assert f.toggle_upvote(b, NOA) and not f.toggle_upvote(b, NOA) and f.toggle_upvote(b, NOA)
    f.reply(b, "Good question")
    posts = f.of_lecture(lid, viewer_id=NOA)
    assert [p["id"] for p in posts] == [b, a]            # most 👍 first
    assert posts[0]["replies"][0]["text"] == "Good question" and posts[0]["upvoted"]
    f.delete_post(b)
    assert [p["id"] for p in f.of_lecture(lid)] == [a]


# ---------------- FR-7: AI settings ----------------
def test_api_key_is_never_returned(env):
    s = LLMSettings(env["conn"])
    assert isinstance(s.client(), OfflineClient)
    s.save("anthropic", "claude-haiku-5-5", "sk-ant-secret-1234567890")
    view = s.public_view()
    assert view["key_set"] and "secret" not in str(view) and view["key_mask"].endswith("7890")
    assert isinstance(s.client(), ClaudeClient)
    s.save("anthropic", "claude-opus-5-5", None)        # empty key field keeps the saved key
    assert s.client().model == "claude-opus-5-5" and s.public_view()["key_set"]
    s.save("openai", "gpt-6-luna", None)                 # a key belongs to one provider
    assert isinstance(s.client(), OfflineClient)
    with pytest.raises(ValueError):
        s.save("nope", "x", "k")


# ---------------- FR-7: AI features (offline path; no network in tests) ----------------
VTT = """WEBVTT

00:00:00.000 --> 00:00:30.000
Um so today we talk about the Open/Closed principle, you know, it is important.

00:00:30.000 --> 00:01:00.000
Um a class should be open for extension. Any questions?
"""


def test_transcript_parsing_and_stats():
    text, cues = parse_transcript(VTT)
    assert "-->" not in text and len(cues) == 2 and cues[1][0] == 30.0
    s = speaking_stats(text, cues)
    assert s["minutes"] == 1.0 and s["fillers"]["um"] == 2 and s["questions_asked"] == 1
    assert s["words_per_minute"] == s["words"]


def test_teaching_feedback_offline_and_empty():
    out = teaching_feedback(VTT, OfflineClient())
    assert "Pace" in out["report"] and out["engine"].startswith("Offline")
    with pytest.raises(ValueError):
        teaching_feedback("WEBVTT\n\n", OfflineClient())


class BrokenLLM(OfflineClient.__mro__[1]):  # an LLMClient whose provider is down
    provider = "anthropic"

    def complete(self, system, prompt):
        raise ConnectionError("no network in class")


def test_ai_falls_back_when_the_provider_fails():
    llm = BrokenLLM("claude-haiku-5-5", "k")
    assert "unavailable" in teaching_feedback(VTT, llm)["note"]
    assert student_summary("A long enough sentence about polymorphism and classes.", llm)["report"]
    out = review_homework({"noa": "def f(): pass", "dan": "def f(): pass"}, "", llm)
    assert out["engine"].startswith("Offline") and out["pairs"][0]["similarity"] >= out["flag_threshold"]


def test_similarity_ignores_comments_and_whitespace():
    pairs = similarity_matrix({"a": "x = 1  # mine\n", "b": "x = 1", "c": "completely different code here"})
    assert pairs[0] == {"a": "a", "b": "b", "similarity": 100}


def test_extractive_summary_keeps_order_and_limit():
    text = " ".join(f"Sentence number {i} talks about polymorphism and interfaces today." for i in range(10))
    out = extractive_summary(text, max_sentences=3)
    assert len(out) == 3 and out == sorted(out, key=text.index)


# ---------------- FR-4.11: export ----------------
def test_excel_export(env):
    from openpyxl import load_workbook
    att, lid = env["att"], open_lecture(env, "Intro")
    env["lectures"].create(env["cid"], "Draft")  # drafts are not exported
    att.open_window(lid, "sound")
    att.heard(NOA, att.issue_token(lid))
    att.set_status(lid, DAN, "late")
    data = ExcelExporter(env["courses"], env["roster"], env["lectures"], att, env["polls"], env["forum"]).build(env["cid"])
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Overview", f"L{lid} Intro", "Polls", "Forum"]
    rows = {r[0]: r[1] for r in wb["Overview"].iter_rows(min_row=2, values_only=True)}
    assert rows == {"Noa Levi": "Present", "Daniel Cohen": "Late"}
