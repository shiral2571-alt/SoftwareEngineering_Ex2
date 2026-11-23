# Statement of Work (SoW)

**Project:** Acoustic Attendance, a web-based teaching tool
**Course:** Introduction to Software Engineering (OOP/OOD), Ex2: *Vibe Coding & Deep Designing: Web-based Teaching Tool*
**Deadline:** 2026-11-25 · **Demo:** in class, 10 minutes
**Related:** [SRS](SRS.md) (requirements and decisions) · [Use cases](USE_CASES.md) · [Components](COMPONENTS.md) · [Diagrams](DIAGRAMS.md) · [Testing strategy](TESTING_STRATEGY.md) · [Tools report](TOOLS_REPORT.md) · [Conclusions](CONCLUSIONS.md)

---

## 1. Background and problem
The assignment states: *"The current use of online tools for teaching are not 'doing it' — we need better, simpler and LLM-ready tools for proper learning."*

Attendance is the main feature. Taking it by hand wastes class time. The usual digital fix is a static QR code or a code on the board, and a photo of it can be sent on WhatsApp to a friend at home. Questions, quick checks of understanding and feedback on teaching are scattered across different tools.

## 2. Objectives
1. Students mark attendance **automatically, or as simply as possible**: one tap, no typing.
2. The lecturer evaluates attendance with a **simple and efficient method**, and gets an **online and offline spreadsheet**.
3. Students **comment and ask questions** in real time or afterwards.
4. The lecturer runs **on-the-spot KISS polls**.
5. The lecturer gets an **AI analysis of the class recording**: feedback on their own teaching.
6. **LLM review of homework**, including comparison between students.
7. It **works in the real classroom**, is shown in a real demo, and is a **KISS smartphone web app**.

## 3. Scope

### 3.1 In scope (what we deliver)
| Area | Deliverable |
|---|---|
| Attendance | Check-in window opened by the lecturer, by **sound** ([ggwave](https://github.com/ggerganov/ggwave)) or a **rotating QR**. Statuses: Present, Late, Absent. Live sheet and Excel export |
| Lecture lifecycle | Each lecture is an object: **Draft → Open → Closed**, with reopen. It stays editable after it is closed |
| Courses | Several courses, each with its own roster (CSV or xlsx, **names only**) |
| Polls | Sets of questions: quiz (correct answer), multiple choice, free text. Prepared in advance, or imported from a template |
| Forum | Per lecture: named or fully anonymous posts, lecturer replies, 👍, delete |
| AI | Teaching feedback from a transcript, a student summary, and homework review with a similarity table. The provider (Claude, Gemini or OpenAI) is selectable |
| Documents | README, SoW, SRS, use cases, components, class and sequence diagrams, testing strategy, tools report, conclusions |
| Demo | A 10-minute live demo with real phones |

### 3.2 Out of scope
Per the assignment guidelines, *"no need to integrate with Moodle, Zoom or personal data"*, and *"you should only design what can be implemented"*:
- Moodle integration: the roster is a file exported by hand.
- Zoom integration, including recording links: the lecturer uploads the transcript instead.
- Personal data beyond names: no ID numbers, no photos of students.
- Multiple lecturer accounts.
- Background listening or presence checks during the lecture: browsers cannot listen in the background.
- Head count from a class photo, and homework review from GitHub links. These are designed but not implemented (SRS §8).

## 4. Approach
- **Design first, then compose.** As the assignment requires, it is a design challenge where "using other code is preferred". We compose existing tools: ggwave for sound, Flask, SQLite, openpyxl, a QR library, and LLM SDKs. Our own code is the domain logic: lectures, attendance rules, polls, forum, prompts.
- **Test tools in real life before relying on them.** Every risky tool was tried on a real phone or with a real lecture transcript (see the [Tools report](TOOLS_REPORT.md)).
- **Iterate from real tests.** Each finding became a recorded decision in the SRS. For example, ultrasound failed on a real phone, so audible sound became the default (D-2). The first sound was missed, so students can now get ready early (D-16).
- **Prioritize with MoSCoW.** Design everything, implement the *Must* items first.

## 5. Key scenarios: registration and attendance
The lecturer asked for a "Happy Case" and "Edge Cases" for student registration and attendance.

### 5.1 Happy case
1. **Before class:** the lecturer imports the class list (names) and creates *Lecture 6* as a **Draft**, with a prepared poll.
2. **First time only:** a student scans the projector's *Join QR*, picks their name from the list, and the phone is linked to that name.
3. The lecturer **opens** the lecture. Students tap **Get ready to check in**, and their phones start listening.
4. The lecturer presses **Start check-in (sound)**. Every phone hears the first code, the server marks the students **Present**, and each phone's microphone closes.
5. The live counter reaches 40/40, and the lecturer presses **End check-in**. Teaching continues.
6. During the lecture, students answer a poll and post questions. After the lecture, the lecturer replies, closes the lecture and downloads the Excel sheet.

### 5.2 Edge cases
| # | Situation | Expected behaviour |
|---|---|---|
| E1 | A phone doesn't hear the sound (far seat, weak speaker, noise) | The lecturer switches to **QR** check-in; if that fails, **manual** marking |
| E2 | A student arrives after check-in ended | Shown as **Absent**; the lecturer sets **Late** by hand |
| E3 | A photo of the QR, or a recording of the sound, is sent to a friend later | Codes expire after 20–30 s and the QR keeps changing, so the code is rejected |
| E4 | Someone already registered my name | Registration is refused; the lecturer presses **reset phone** |
| E5 | A student picks the wrong name | Picking the right name releases the wrong one |
| E6 | One phone tries to check in two students | Refused for the second name in the same lecture |
| E7 | No microphone, or permission denied | QR check-in |
| E8 | A student follows from home on Zoom | Absent, but can still answer polls and use the forum |
| E9 | The lecturer closes the lecture by mistake | **Reopen** |
| E10 | No internet or an invalid AI key | Clear message and offline fallback; the rest of the app keeps working |
| E11 | Inappropriate anonymous post | The lecturer deletes it |
| E12 | Duplicate names in the roster | Import is refused, and the lecturer is asked to tell the names apart |
| E13 | A student in class relays the sound **live** to a friend at home, e.g. over a WhatsApp call, within the 20 s window | **Accepted risk.** It needs a live accomplice in every lecture. The lecturer compares the counter with the room. See SRS E13 |

## 6. Deliverables and status
| # | Assignment To-Do | Deliverable | Status |
|---|---|---|---|
| 1 | Repository, problem and scope | [README](../README.md) | ✅ |
| 2 | Submit via the form | Repository link | At submission |
| 3 | Tools report, tested in real life | [TOOLS_REPORT.md](TOOLS_REPORT.md) | ✅ |
| 4 | SoW | This document | ✅ |
| 5 | SRS | [SRS.md](SRS.md) | ✅ |
| 6 | Main use cases (client stories) | [USE_CASES.md](USE_CASES.md) | ✅ |
| 7 | Main software components | [COMPONENTS.md](COMPONENTS.md) | ✅ |
| 8 | Low-level class and sequence diagrams | [DIAGRAMS.md](DIAGRAMS.md) | ✅ |
| 9 | Testing strategy addressing the classes | [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | ✅ |
| 10 | Demo KISS web app (vibe code vs. find and compose) | `app/` + [README](../README.md) | ✅ |
| 11 | Demo in class | Live, 10 minutes | Planned |
| 12 | Conclusions | [CONCLUSIONS.md](CONCLUSIONS.md) | ✅ |

## 7. Timeline (actual)
| Date | Milestone |
|---|---|
| 2026-11-08 | Concept agreed; sound spike tested on a real phone; repository created |
| 2026-11-10 | First demo app; first full-app phone test (audible works, ultrasound short range) |
| 2026-11-13 | Requirements check against the assignment; names-only registration |
| 2026-11-16 | Requirements review with the team; SRS with MoSCoW; app rebuilt around the SRS |
| 2026-11-17 | Phone test of "get ready early"; real lecture transcript tested with Gemini |
| 2026-11-23 | SoW, use cases, components, diagrams, testing strategy, tools report, conclusions |
| 2026-11-24 | Demo rehearsal with several phones; merge to `main` |
| 2026-11-25 | Submission |

## 8. Risks and mitigations
| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R-1 | The sound does not reach the back rows of the large lecture hall | Low–Medium | Audible sound by default; rotating QR as an equal alternative; manual marking. Go/no-go test in the hall before the demo. **Tested 11-23:** audible reached the back of the empty auditorium (iPhone 17 Pro Max) |
| R-2 | The demo network blocks the HTTPS tunnel. This happened on one network, where the laptop could not resolve the tunnel address | Medium | Phones use mobile data; the lecturer dashboard runs on `localhost`; a backup network (phone hotspot) |
| R-3 | The AI provider is down, or the key is invalid, during the demo | Low | Offline fallback for every AI feature; a report prepared in advance in the lecture's materials |
| R-4 | A live relay of the code (E13) | Low | Accepted and documented; the lecturer compares the count with the room |
| R-5 | The scope grows beyond the time available | High (it did) | MoSCoW: Should/Could items were cut first (homework review from GitHub links, video upload) |

## 9. Team and roles
Two students. Responsibilities were shared: concept and design decisions, real-life tests with phones and transcripts, the teaching-feedback prompt, and review of all documents. The code and first drafts were produced with an AI coding assistant ("vibe coding") under the team's direction, then tested and corrected by the team.
