# Acoustic Attendance — a web-based teaching tool

Ex2, Introduction to Software Engineering (OOP/OOD).

## Problem
Taking attendance by hand wastes lecture time. The usual fix is a static QR code or a code on the board, and a photo of it gets sent on WhatsApp to a friend at home. Students' questions and quick checks of understanding are also scattered across different tools, and the lecturer gets little feedback on their own teaching.

## Our solution (scope)
One simple web app per course, built around **the lecture as an object**: *Draft → Open → Closed*, and everything stays editable after the lecture.
- **Attendance:** at a moment the lecturer chooses, the laptop plays a short-lived code as **sound** ([ggwave](https://github.com/ggerganov/ggwave)) or shows a **rotating QR**. Students check in with one tap. The microphone opens for a few seconds and closes again.
- **Polls, a forum and AI tools** are attached to each lecture.

Every requirement, priority (MoSCoW) and design decision is in **[docs/SRS.md](docs/SRS.md)**. Background: [docs/CONCEPT.md](docs/CONCEPT.md).

| # | Assignment feature | In the app |
|---|---|---|
| 1 | Automatic attendance + spreadsheet | Check-in window by sound or rotating QR; Present / Late / Absent, editable by the lecturer; live sheet + Excel per course |
| 2 | Comments & suggestions | A forum per lecture: named or **fully anonymous** posts, lecturer replies, 👍 "me too", delete |
| 3 | KISS polls | Sets of questions prepared in advance (in the app or from an xlsx/csv template): quiz with a correct answer, multiple choice, free text |
| 4 | ML summary of class video | **Teaching feedback for the lecturer**: upload the Zoom transcript → measured pace and filler words + short AI feedback |
| 5 | LLM homework review | Per-student review + cross-student similarity table |

**AI provider:** choose Claude, Gemini or OpenAI and a model in ⚙ Settings, and paste an API key. The key stays on the server. Without a key, offline fallbacks run.
**Out of scope:** Moodle/Zoom integration, and personal data beyond names (the lecturer's list has no ID numbers). See SRS §8 for everything marked *Won't*.

## Run it
```bash
py -m pip install -r requirements.txt
py run.py
```
The server prints the lecturer dashboard address (`http://localhost:5000/lecturer`) and a **lecturer PIN**. To use a fixed PIN, set `LECTURER_PIN` first.
On the first run, a demo course with the fictional `data/sample_roster.csv` is created.

Phones need HTTPS for the microphone, so open a tunnel in a second terminal:
```bash
cloudflared tunnel --url http://localhost:5000
```
Open the dashboard on the laptop **through the `https://…trycloudflare.com` link**, so the QR codes point to an address phones can reach.

## Demo script (10 min)
1. **Course list:** import the class list (CSV/xlsx with a `name` column), or keep the sample course.
2. **Prepare:** create *Lecture 6* (it starts as **Draft**, so students can't see it). Add a poll, or import one from the template.
3. **Open** the lecture and press **📱 Join QR**. Students scan it and pick their name, once per phone.
4. **🔊 Start check-in (sound):** students tap **Check in**, and the sheet fills live. Press **■ End check-in**. Set a latecomer to **Late** by hand.
5. Show the fallback: **🔲 Start check-in (QR)**, a code that changes every 15 s.
6. **Polls:** press **▶ Launch** and show the live bars and the % correct.
7. **Forum:** an anonymous question gets 👍 votes, and you reply.
8. **Materials & AI:** upload `data/demo/lecture_transcript.vtt` and get **teaching feedback**. For homework review, use `data/demo/homework/*.py`; Noa and Maya are flagged as similar.
9. **■ Close** the lecture, then show that you can still edit it, or **↺ Reopen** it. Download **⬇ Excel**.

## Tests
```bash
py -m pytest -q
```
- `tests/test_services.py` tests each service class with a fake clock: lecture lifecycle, token expiry, check-in windows, polls, the forum, AI fallbacks and the export.
- `tests/test_routes.py` runs the phone and lecturer flows through the HTTP API.

## Project layout
```
app/
  roster.py          RosterSource (interface) · Csv/XlsxRosterSource · CourseService · CourseRoster
  identity.py        DeviceRegistry: one name ↔ one phone (HttpOnly cookie), lecturer reset
  lectures.py        LectureService (Draft → Open → Closed, reopen) · MaterialService
  attendance.py      AttendanceService: check-in windows, tokens, Present / Late / Absent
  polls.py           PollService · Question · xlsx/csv import + template
  forum.py           ForumService: posts, replies, 👍, delete
  llm.py             LLMClient (interface) · ClaudeClient · GeminiClient · OpenAIClient · OfflineClient · LLMSettings
  ai_tools.py        teaching feedback · student summary · homework review
  export.py          ExcelExporter
  routes_*.py        Flask routes (thin; logic lives in the services)
  static/sound.js    ggwave broadcast / listen
  templates/         student.html (phone) · lecturer.html (laptop / projector)
spike/sound-test/    the original proof-of-concept page used for the real-device tests
docs/                SRS.md · CONCEPT.md · REQUIREMENTS_CHECK.md · SCHEDULE.md
```
