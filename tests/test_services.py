"""Unit tests for the service classes (no browser, no sound — the sound layer only delivers a token string)."""
import pytest

from app import db as dbmod
from app.ai_tools import OfflineClient, extractive_summary, review_homework, similarity_matrix, split_transcript, summarize_lecture
from app.attendance import PULSE_WINDOW, SOUND_TOKEN_TTL, TOKEN_ALPHABET, TOKEN_LENGTH, AttendanceService, attendance_status
from app.engagement import CommentService, PollService
from app.export import ExcelExporter
from app.identity import DeviceRegistry
from app.roster import CourseRoster, CsvRosterSource, Student, key_for_name

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
    roster.replace_all(CsvRosterSource(ROSTER_CSV))
    return dict(conn=conn, clock=clock, roster=roster, devices=DeviceRegistry(conn, roster, clock),
                att=AttendanceService(conn, clock), polls=PollService(conn, clock), comments=CommentService(conn, clock))


# ---------------- Roster & identity ----------------
def test_names_only_csv_gets_stable_keys():
    students = CsvRosterSource("﻿Name\nNoa  Levi\n\n").load()
    assert [s.name for s in students] == ["Noa Levi"]
    assert students[0].student_id == key_for_name("noa levi")  # same key on re-import


def test_csv_first_and_last_name_columns():
    assert CsvRosterSource("First Name,Last Name\nNoa,Levi\n").load()[0].name == "Noa Levi"


def test_csv_optional_id_column_is_kept():
    assert CsvRosterSource("ID,Full Name\n1234,A B\n").load() == [Student("1234", "A B")]


def test_csv_without_name_column_or_with_duplicates_is_rejected():
    with pytest.raises(ValueError):
        CsvRosterSource("id,email\n1,a@b.c\n").load()
    with pytest.raises(ValueError):
        CsvRosterSource("name\nNoa Levi\nnoa levi\n").load()


def test_find_by_name_ignores_case_and_spaces(env):
    r = env["roster"]
    assert r.find_by_name("  noa   LEVI ").name == "Noa Levi"
    assert r.find_by_name("Noa") is None


def test_first_phone_owns_the_name(env):
    d, noa = env["devices"], env["roster"].find_by_name("Noa Levi")
    first = d.claim(noa)
    assert first.ok and d.student_for(first.device_token) == noa
    assert d.claim(noa, first.device_token).device_token == first.device_token  # same phone again: fine
    assert not d.claim(noa, "other-phone").ok                                   # someone else: refused
    assert d.student_for("forged") is None and d.student_for(None) is None


def test_switching_name_releases_the_old_one(env):
    d, r = env["devices"], env["roster"]
    noa, dan = r.find_by_name("Noa Levi"), r.find_by_name("Daniel Cohen")
    tok = d.claim(noa).device_token
    d.claim(dan, tok)  # picked the wrong name first, then corrected it
    assert not d.is_registered(noa.student_id) and d.claim(noa).ok


def test_lecturer_reset_frees_the_name(env):
    d, noa = env["devices"], env["roster"].find_by_name("Noa Levi")
    tok = d.claim(noa).device_token
    d.reset(noa.student_id)
    assert d.student_for(tok) is None and d.claim(noa, "real-noa-phone").ok


# ---------------- Tokens & check-in ----------------
def test_token_format(env):
    lec = env["att"].start_lecture("L1")
    tok = env["att"].issue_token(lec)
    assert len(tok) == TOKEN_LENGTH and set(tok) <= set(TOKEN_ALPHABET)


def test_valid_token_checks_in_once(env):
    att = env["att"]
    lec = att.start_lecture("L1")
    tok = att.issue_token(lec)
    assert att.heard(NOA, tok).message == "Checked in"
    assert att.heard(NOA, tok).message == "Already checked in"
    s = att.student_summary(lec, NOA)
    assert s["checked_in"] and s["method"] == "sound"


def test_expired_token_is_rejected(env):
    att, clock = env["att"], env["clock"]
    lec = att.start_lecture("L1")
    tok = att.issue_token(lec)
    clock.advance(SOUND_TOKEN_TTL + 1)  # e.g. a recording replayed to a friend later
    res = att.heard(NOA, tok)
    assert not res.ok and res.message == "Code expired"
    assert not att.student_summary(lec, NOA)["checked_in"]


def test_unknown_and_lowercase_tokens(env):
    att = env["att"]
    lec = att.start_lecture("L1")
    assert not att.heard(NOA, "ZZZZZZ").ok
    assert att.heard(NOA, att.issue_token(lec).lower()).ok


def test_token_from_previous_lecture_is_rejected(env):
    att = env["att"]
    old = att.start_lecture("L1")
    tok = att.issue_token(old)
    att.start_lecture("L2")  # ends L1
    assert not att.heard(NOA, tok).ok


def test_qr_channel_is_recorded(env):
    att = env["att"]
    lec = att.start_lecture("L1")
    att.heard(NOA, att.issue_token(lec, "qr"))
    assert att.student_summary(lec, NOA)["method"] == "qr"


def test_manual_check_in(env):
    att = env["att"]
    lec = att.start_lecture("L1")
    att.manual_check_in(lec, DAN)
    assert att.student_summary(lec, DAN)["method"] == "manual"


# ---------------- Pulses ----------------
def test_pulse_token_counts_for_pulse(env):
    att, clock = env["att"], env["clock"]
    lec = att.start_lecture("L1")
    att.heard(NOA, att.issue_token(lec))
    pulse = att.start_pulse(lec)
    res = att.heard(NOA, att.issue_token(lec))
    assert res.kind == "pulse" and att.heard_pulse(pulse, NOA)
    clock.advance(PULSE_WINDOW + 1)
    assert att.active_pulse(lec) is None
    att.start_pulse(lec)  # Noa misses the second pulse
    s = att.student_summary(lec, NOA)
    assert (s["pulses_heard"], s["pulses_total"]) == (1, 2)


def test_hearing_a_pulse_also_checks_in_late_arrival(env):
    att = env["att"]
    lec = att.start_lecture("L1")
    att.start_pulse(lec)
    att.heard(DAN, att.issue_token(lec))
    assert att.student_summary(lec, DAN)["checked_in"]


def test_attendance_status_without_pulses():
    # Only the cases that do not depend on the pulse policy (still to be decided — see attendance_status).
    assert attendance_status(True, 0, 0) == "Present"
    assert attendance_status(False, 0, 0) == "Absent"
    assert attendance_status(False, 0, 3) == "Absent"


# ---------------- Polls & comments ----------------
def test_poll_vote_once_and_counts(env):
    p, att = env["polls"], env["att"]
    lec = att.start_lecture("L1")
    pid = p.create(lec, "Clear?", ["Yes", "No", ""])
    assert p.vote(pid, NOA, 0)
    assert not p.vote(pid, NOA, 1)  # second vote ignored
    assert not p.vote(pid, DAN, 5)  # no such option
    assert p.open_poll(lec)["counts"] == [1, 0]
    p.close(pid)
    assert p.open_poll(lec) is None and not p.vote(pid, DAN, 1)


def test_poll_validation_and_one_open_poll(env):
    p, lec = env["polls"], env["att"].start_lecture("L1")
    with pytest.raises(ValueError):
        p.create(lec, "Only one option?", ["Yes"])
    first = p.create(lec, "Q1", ["a", "b"])
    p.create(lec, "Q2", ["a", "b"])
    assert p.open_poll(lec)["question"] == "Q2" and not p.vote(first, NOA, 0)


def test_anonymous_comment_hides_name(env):
    c, lec = env["comments"], env["att"].start_lecture("L1")
    c.add(lec, NOA, "Slower please", anonymous=True)
    c.add(lec, DAN, "Great example", anonymous=False)
    authors = [x["author"] for x in c.for_lecture(lec)]
    assert authors == ["Daniel Cohen", "Anonymous"]
    with pytest.raises(ValueError):
        c.add(lec, NOA, "   ", anonymous=False)


# ---------------- Export ----------------
def test_excel_export_has_expected_sheets(env):
    from openpyxl import load_workbook
    import io
    att = env["att"]
    lec = att.start_lecture("Intro")
    att.heard(NOA, att.issue_token(lec))
    data = ExcelExporter(env["roster"], att, env["devices"], env["polls"], env["comments"]).build()
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Overview", f"L{lec} Intro", "Polls", "Comments"]
    rows = {r[1]: r[2] for r in wb["Overview"].iter_rows(min_row=2, values_only=True)}
    assert rows == {"Noa Levi": "Present", "Daniel Cohen": "Absent"}


# ---------------- AI tools (offline path; Claude is not called in tests) ----------------
def test_vtt_timing_lines_are_removed():
    text = split_transcript("WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\nHello <b>class</b>.\n")
    assert text == "Hello class."


def test_extractive_summary_keeps_order_and_limit():
    text = " ".join(f"Sentence number {i} talks about polymorphism and interfaces today." for i in range(10))
    out = extractive_summary(text, max_sentences=3)
    assert len(out) == 3 and out == sorted(out, key=text.index)


def test_summary_offline_and_empty():
    assert summarize_lecture("Polymorphism lets one interface have many forms in our code.", OfflineClient())["summary"]
    with pytest.raises(ValueError):
        summarize_lecture("WEBVTT\n\n", OfflineClient())


def test_similarity_ignores_comments_and_whitespace():
    pairs = similarity_matrix({"a": "x = 1  # mine\n", "b": "x = 1", "c": "completely different code here"})
    assert pairs[0] == {"a": "a", "b": "b", "similarity": 100}


class BrokenLLM:
    name = "broken"

    def complete(self, system, prompt):
        raise ConnectionError("no network in class")


def test_homework_review_falls_back_when_llm_fails():
    out = review_homework({"noa": "def f(): pass", "dan": "def f(): pass"}, "", BrokenLLM())
    assert out["engine"].startswith("Offline") and set(out["reviews"]) == {"noa", "dan"}
    assert out["pairs"][0]["similarity"] >= out["flag_threshold"]
