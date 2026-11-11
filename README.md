# Acoustic Attendance — a web-based teaching tool

Ex2, Introduction to Software Engineering (OOP/OOD).

## Problem
Taking attendance by hand wastes lecture time. The usual fixes, a static QR code or a code on the board, have two holes:
- **Remote cheating.** A photo of the code gets sent on WhatsApp.
- **Check-in only.** A student can register in the first minute and leave.

## Our solution (scope)
**The classroom itself proves presence.** The lecturer's laptop broadcasts a short-lived token as near-inaudible sound
([ggwave](https://github.com/ggerganov/ggwave)), and students' phones hear it and check in. The same sound repeats as
random **presence pulses** during the lecture, so the spreadsheet shows *being there*, not just *arriving*.
Full concept: [docs/CONCEPT.md](docs/CONCEPT.md).

| # | Feature | In the demo |
|---|---|---|
| 1 | Automatic attendance + spreadsheet | Sound check-in, random pulses, rotating-QR fallback, manual override; live online sheet plus offline Excel export |
| 2 | Comments & suggestions | Phone → live feed, optionally anonymous |
| 3 | KISS polls | One question, 2–4 options, live bars; can double as a presence pulse |
| 4 | ML summary of class video | Upload the recording's transcript (.vtt/.srt/.txt) → Claude summary (offline extractive summary without an API key) |
| 5 | LLM homework review | Upload submissions → per-student review, class comparison and a similarity table |

**Out of scope:** Moodle/Zoom integration and personal data beyond name + student ID. The roster is a CSV file that can be exported from Moodle.
Video-to-text transcription is also out of scope: we use the transcript the recording platform already produces.

## Run it
```bash
py -m pip install -r requirements.txt
py run.py
```
The server prints the lecturer dashboard address (`http://localhost:5000/lecturer`) and a **lecturer PIN**.
To use a fixed PIN, set `LECTURER_PIN` first.

Phones need HTTPS for the microphone, so open a tunnel in a second terminal:
```bash
cloudflared tunnel --url http://localhost:5000
```
Open the dashboard on the laptop **through the `https://…trycloudflare.com` link**, so the QR codes point to an address phones can reach.

Optional: set `ANTHROPIC_API_KEY` to get Claude summaries and reviews. Without it, the app uses offline fallbacks and the demo still works.

## Demo script (10 min)
1. **Settings:** import the course CSV, or keep the fictional `data/sample_roster.csv`.
2. **Start lecture.** Press **📱 Join QR** on the projector so students scan it, pick their name and enter the last 4 ID digits (once per phone).
3. Students tap **Join class**. You press **🔊 Start check-in sound**, and the sheet fills up live.
4. Show the fallback: **🔲 QR check-in** (rotates every 15 s) and **✓ manual**.
5. Press **📡 Presence pulse now**. The projector banner appears, and the *Pulses* column goes up only for phones that are still in the room.
6. **Polls & comments:** use *Ask + presence pulse*, and show comments arriving.
7. **AI tools:** use `data/demo/lecture_transcript.vtt` and `data/demo/homework/*.py`. Noa and Maya are flagged as similar.
8. **⬇ Excel:** download the offline spreadsheet (overview, one sheet per lecture, polls, comments).

## Tests
```bash
py -m pytest -q
```
`tests/test_services.py` tests each service class with a fake clock (token expiry, pulses, polls and more).
`tests/test_routes.py` runs the phone and lecturer flows through the HTTP API.

## Project layout
```
app/
  roster.py       RosterSource (interface) · CsvRosterSource · CourseRoster
  identity.py     DeviceRegistry: phone ↔ student binding (HttpOnly cookie)
  attendance.py   AttendanceService: lectures, tokens, check-ins, pulses · attendance_status()
  engagement.py   PollService · CommentService
  ai_tools.py     LLMClient (interface) · ClaudeClient · OfflineClient · summary & homework review
  export.py       ExcelExporter
  __init__.py     Flask routes (thin; logic lives in the services)
  static/sound.js ggwave broadcast / listen
  templates/      student.html (phone) · lecturer.html (laptop / projector)
spike/sound-test/ the original proof-of-concept page used for the real-device tests
docs/             CONCEPT.md · SCHEDULE.md
```
