# Software Requirements Specification (SRS)

**Project:** Acoustic Attendance — a web-based teaching tool
**Course:** Introduction to Software Engineering (OOP/OOD), Ex2
**Version:** 0.2 · 2026-11-16 (status column updated after implementation)
**Related documents:** [README](../README.md) · [CONCEPT](CONCEPT.md) · [REQUIREMENTS_CHECK](REQUIREMENTS_CHECK.md)

---

## 1. Introduction

### 1.1 Purpose
This document specifies what the system must do and why. Every design decision agreed by the team is recorded here, and each requirement has a priority. Design documents (components, class and sequence diagrams) and the testing strategy are derived from this document.

### 1.2 Scope
A web application for **one lecturer** and the **students** of their courses. Students use it on their smartphones, in the browser, with no installation. The lecturer uses it on the classroom laptop and projector.

| # | Assignment feature | Covered by |
|---|---|---|
| 1 | Automatic attendance + online/offline spreadsheet (**main feature**) | §4.4 Attendance |
| 2 | Comments and suggestions, real time / offline | §4.6 Forum |
| 3 | On-the-spot KISS polls | §4.5 Polls |
| 4 | ML summary of the class video | §4.7.2 Teaching feedback |
| 5 | Deep LLM review of homework with comparison | §4.7.3 Homework review |

### 1.3 Definitions
| Term | Meaning |
|---|---|
| **Course** | A group of lectures with its own student list (roster) |
| **Lecture** | One class meeting. It is an object with a lifecycle: Draft → Open → Closed (§3) |
| **Roster** | The list of students in a course: **names only**, no ID numbers |
| **Check-in** | A student proving presence in a lecture, by sound or by QR |
| **Check-in window** | A short period, opened by the lecturer, during which check-in is possible |
| **Token** | A short random code (6 characters) that the server issues for one check-in window |
| **Sound check-in** | The laptop plays the token as sound ([ggwave](https://github.com/ggerganov/ggwave)); phones decode it |
| **Poll** | A set of one or more questions that the lecturer launches during or after a lecture |
| **LLM provider** | An external AI service: Anthropic (Claude), Google (Gemini) or OpenAI |
| **MoSCoW** | Priority: **M**ust, **S**hould, **C**ould, **W**on't (now) |

### 1.4 Priorities (MoSCoW)
- **Must:** required for the demo; the project fails without it.
- **Should:** important; planned for the demo if time allows.
- **Could:** nice to have.
- **Won't (now):** designed and justified here, but **not implemented**. The assignment says "you should only design what can be implemented".

---

## 2. Overall description

### 2.1 Users
| User | Device | Goals |
|---|---|---|
| **Lecturer** (exactly one) | Laptop + projector | Run lectures, take attendance with minimal class time, ask polls, answer questions, get AI feedback |
| **Student** | Own smartphone (browser) | Check in with one tap, answer polls, ask questions (optionally anonymously) |

### 2.2 Operating environment
- **Server:** Python + Flask + SQLite, running on the lecturer's laptop.
- **Network:** phones reach the server through an HTTPS tunnel (Cloudflare). HTTPS is required for microphone access.
- **Phones:** iPhone with Safari and Android with Chrome, current versions.

### 2.3 Constraints (from the assignment)
- **CON-1** No integration with Moodle or Zoom, and no personal data beyond the student's name.
- **CON-2** Design only what can be implemented.
- **CON-3** KISS: a simple smartphone web app.
- **CON-4** It must work in the real classroom (a large lecture hall) and be demoed in about 10 minutes.
- **CON-5** Composing existing code is preferred over writing everything.

### 2.4 Assumptions
- **AS-1** University students are trusted to behave like adults. For example, anonymous questions are not abused, and the lecturer can delete them if needed.
- **AS-2** The lecture pauses for 1–2 minutes during check-in, because everyone is busy with their phones anyway. So an audible check-in sound does not disturb teaching.
- **AS-3** The lecturer can export a names list (CSV or Excel) from Moodle by hand.

---

## 3. Domain model: the lecture as an object

```
Lecturer 1 ── * Course 1 ── * Lecture
                 │              ├── * AttendanceRecord (student, status, method, time)
                 │              ├── * Poll ── * Question ── * Answer
                 │              ├── * ForumPost ── * Reply
                 │              └── * Material (files, summaries, AI reports)
                 └── * Student (name, linked phone)
```

**Lecture lifecycle**

```
 [Draft] ──open──▶ [Open] ──close──▶ [Closed]
                     ▲                  │
                     └────reopen────────┘
```

| State | Lecturer | Students |
|---|---|---|
| **Draft** | Prepares the lecture: title, polls in advance, materials | **Cannot see it** |
| **Open** | Runs check-in windows, launches polls, answers questions | See it; can check in (during a window), answer polls and post |
| **Closed** | Can still edit **everything**: attendance, polls, replies, materials, AI reports | Can still read and post in the forum; cannot check in |

---

## 4. Functional requirements

Format: **ID · requirement · priority**. Status in the current demo: ✅ exists · 🔧 to build or change.

### 4.1 Lecturer access
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-1.1 | A single lecturer logs in with a PIN | Must | ✅ |
| FR-1.2 | Multiple lecturers with personal accounts | Won't | — |

### 4.2 Courses and roster
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-2.1 | The lecturer creates courses; each course has its own roster and lectures | Must | ✅ |
| FR-2.2 | Roster import from CSV or xlsx: a *name* column, or *first name* + *last name*. Hebrew headers are accepted. No ID numbers are needed | Must | ✅ |
| FR-2.3 | Re-importing the same list keeps past attendance (stable internal key per name) | Must | ✅ |

### 4.3 Lectures
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-3.1 | The lecturer creates a lecture in **Draft**. Only the lecturer sees drafts | Must | ✅ |
| FR-3.2 | The lecturer **opens** a lecture; students now see it | Must | ✅ |
| FR-3.3 | The lecturer **closes** a lecture and can **reopen** it, for example after closing by mistake | Must | ✅ |
| FR-3.4 | A lecture list per course: open any past lecture and view or edit its attendance, polls, forum and materials | Must | ✅ |
| FR-3.5 | Upload files and summaries to a lecture (materials) | Should | ✅ |

### 4.4 Attendance (main feature)
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-4.1 | **Registration:** once per phone, the student picks their name from the roster. One name ↔ one phone. Another phone choosing a taken name is refused. Picking a different name on the same phone releases the old one | Must | ✅ |
| FR-4.2 | The lecturer can **reset** a name, for example when a student gets a new phone or someone took a name that isn't theirs | Must | ✅ |
| FR-4.3 | **Check-in window:** the lecturer opens a short check-in window at a moment they choose, by **sound** or by **QR**. **There is no automatic stop:** the window closes only when the lecturer ends it (D-14). Whoever missed it is late | Must | ✅ |
| FR-4.4 | **Sound check-in:** the laptop re-broadcasts a fresh token every ~10 s while the window is open. The student taps *Join class*, the **mic opens, hears one valid token and closes immediately** | Must | ✅ |
| FR-4.5 | **Audible sound by default.** Ultrasound is an option in Settings (§7, D-2) | Must | ✅ |
| FR-4.6 | **QR check-in:** the projector shows a QR code that changes every ~15 s; students scan it with the phone camera | Must | ✅ |
| FR-4.7 | Tokens are short-lived (≈20 s sound, ≈30 s QR) and valid only for the current lecture. The server rejects unknown, expired or foreign tokens | Must | ✅ |
| FR-4.8 | **Statuses:** *Present* (checked in during a window), *Late*, *Absent*. **Late is set only by the lecturer, by hand.** The lecturer can change any status manually, also after the lecture is closed | Must | ✅ |
| FR-4.9 | A phone that already checked in a student in this lecture cannot switch to another name in the same lecture | Must | ✅ |
| FR-4.10 | **Live attendance sheet:** counter (e.g. 32/40), status per student, time, method, and whether a phone is linked | Must | ✅ |
| FR-4.11 | **Offline sheet:** Excel export per lecture and a course overview (students × lectures) | Must | ✅ |
| FR-4.12 | Attendance and participation are **separate**: a student who is Absent or Late, for example watching from home on Zoom, can still answer polls and post in the forum | Must | ✅ |
| FR-4.13 | Head count from a class photo as a sanity check | Won't | — |
| FR-4.14 | Presence pulses during the lecture, a check-out sound, continuous listening | Won't | removed |

### 4.5 Polls
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-5.1 | A poll is a **set of one or more questions** | Must | ✅ |
| FR-5.2 | **Quiz questions:** multiple choice with a marked correct answer. The lecturer chooses whether students see the correct answer after answering | Must | ✅ |
| FR-5.3 | **Feedback questions:** multiple choice without a correct answer | Must | ✅ |
| FR-5.4 | **Free-text answers**, only for feedback questions (e.g. "How was the lecture?"). Quiz questions are never free text | Should | ✅ |
| FR-5.5 | Polls are prepared **in advance** inside the app, as part of a Draft or Open lecture, and launched with one click during the lecture. They can also be launched after the lecture | Must | ✅ |
| FR-5.6 | Poll import from **xlsx or csv** in a fixed format, with a downloadable template: `question, type, option1..option4, correct` | Should | ✅ |
| FR-5.7 | One answer per student per question; live results as bars; for quizzes, the % correct | Must | ✅ |
| FR-5.8 | Polls and results stay available in the lecture after it is closed | Must | ✅ |

### 4.6 Forum: questions and comments
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-6.1 | Each lecture has a **forum tab**. Students post questions or comments, during or after the lecture | Must | ✅ |
| FR-6.2 | The student chooses **named** or **anonymous**. Anonymous means **fully anonymous**: no name is stored, not even for the lecturer | Must | ✅ |
| FR-6.3 | The lecturer **replies** to a post, and students see the reply | Must | ✅ |
| FR-6.4 | The lecturer can **delete** a post | Must | ✅ |
| FR-6.5 | 👍 "Me too" on a question, so the lecturer sees what matters most to the class | Should | ✅ |

### 4.7 AI tools

#### 4.7.1 AI settings
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-7.1 | The lecturer chooses a **provider** (Anthropic Claude, Google Gemini, OpenAI) and a **model**, and pastes an **API key** | Must | ✅ |
| FR-7.1a | **Model list:** for each provider, the 2–3 best-known models, from a **cheap/fast** one (usually usable on a free tier where the provider offers one) up to the **strongest** one. Exact model IDs are confirmed when implemented, and a "custom model ID" field covers newer models | Must | ✅ |
| FR-7.1b | After a key is entered, the list is refreshed from the provider's own *list models* endpoint, so it stays current | Could | 🔧 |
| FR-7.2 | The key is stored **on the server only**, never sent to the browser, and shown masked (e.g. `sk-…abcd`) | Must | ✅ |
| FR-7.3 | A **Test connection** button | Must | ✅ |
| FR-7.4 | Without a key, AI features fall back to offline methods, and the screen says so | Must | ✅ |

#### 4.7.2 Teaching feedback (feature 4, for the **lecturer only**)
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-7.5 | Upload a **transcript** (.vtt, .srt or .txt; Zoom produces one automatically) to a lecture | Must | ✅ |
| FR-7.6 | A **ready-made prompt** is sent with the transcript to the selected provider and model. It returns a **short** teaching-feedback report: clarity, pace, filler words, long monologues, suggestions | Must | ✅ |
| FR-7.7 | Offline statistics from the transcript timestamps: words per minute and filler-word count | Should | ✅ |
| FR-7.8 | Upload a **video or audio** file, which is transcribed first. This needs a provider with speech-to-text (OpenAI or Gemini); Claude has none | Could | 🔧 |
| FR-7.9 | The lecturer edits the ready-made prompt | Could | 🔧 |
| FR-7.10 | A lecture summary **for students** | Could | ✅ |
| FR-7.11 | A link (URL) to a Zoom recording | Won't | — |
| FR-7.12 | The report is saved in the lecture's materials | Should | ✅ |

#### 4.7.3 Homework review (feature 5)
| ID | Requirement | Priority | Demo |
|---|---|---|---|
| FR-7.13 | Upload submissions (one file per student) → per-student LLM review | Must | ✅ |
| FR-7.14 | Cross-student comparison: a similarity table (deterministic, no LLM). High similarity is flagged as "check", never as an automatic verdict | Must | ✅ |
| FR-7.15 | Review from a **list of GitHub repository links**. The lecturer provided a list of Ex1 repositories for testing | Should | 🔧 |

---

## 5. Non-functional requirements
| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Usability (KISS) | A student checks in with **at most 2 taps** after the first registration. No typing, no app installation |
| NFR-2 | Usability | The lecturer starts a check-in window with **one click** |
| NFR-3 | Performance | 40 phones complete check-in within **60 seconds** of the window opening |
| NFR-4 | Privacy | The microphone is open **only** during the student's own check-in, for a few seconds. Sound is decoded **inside the phone's browser**; only the 6-character token reaches the server |
| NFR-5 | Privacy | Only names are stored; no ID numbers. Fully anonymous posts store no student reference |
| NFR-6 | Security | API keys stay on the server, and the lecturer pages require the PIN |
| NFR-7 | Security | Students cannot fake attendance from outside the room: tokens are short-lived and issued only while a window is open, and QR codes rotate |
| NFR-8 | Reliability | There is always a fallback: sound → QR → manual. An AI failure never blocks the rest of the app |
| NFR-9 | Compatibility | Works on iPhone Safari and Android Chrome over HTTPS |
| NFR-10 | Maintainability | Replaceable parts sit behind interfaces: `RosterSource` (CSV/xlsx/Moodle later), `LLMClient` (Claude/Gemini/OpenAI), check-in channel (sound/QR). New options are added without changing existing code (Open/Closed principle) |
| NFR-11 | Testability | Time-dependent logic (token expiry) uses an injectable clock, so it can be unit-tested |

---

## 6. Key scenarios

### 6.1 Happy case: attendance
1. The lecturer opens the lecture and presses **Start check-in (sound)**.
2. Students tap **Join class**. Each phone hears the sound, the mic closes, and the screen shows "✅ You're checked in".
3. The live counter reaches 40/40, and the lecturer stops the window and continues teaching.

### 6.2 Edge cases
| # | Situation | System behaviour |
|---|---|---|
| E1 | The phone doesn't hear the sound (far seat, weak speaker, noise) | The lecturer switches to QR. If that fails too, the lecturer marks the student manually |
| E2 | The student arrives after the window closed | The student is Absent; the lecturer sets **Late** by hand |
| E3 | A friend sends a photo of the QR or a recording of the sound | Tokens expire in 20–30 s and the QR keeps changing |
| E4 | Someone already took my name | Registration is refused with a message; the lecturer presses **reset phone** |
| E5 | A student picks the wrong name | They pick the right name; the wrong one is released |
| E6 | A phone tries to check in two students | Refused for the second name in the same lecture (FR-4.9) |
| E7 | The student denies microphone permission or the phone has no mic | QR check-in |
| E8 | A student studies from home on Zoom | Absent, but can still answer polls and post in the forum (FR-4.12) |
| E9 | The lecturer closes the lecture by mistake | Reopen (FR-3.3) |
| E10 | Invalid AI key or no internet | Clear message and offline fallback (FR-7.4) |
| E11 | Inappropriate anonymous post | The lecturer deletes it (FR-6.4) |
| E12 | The roster has duplicate names | Import is refused with a message telling the lecturer to tell the names apart |

---

## 7. Decision log
| # | Date | Decision | Rationale |
|---|---|---|---|
| D-1 | 2026-11-08 | Attendance by **sound** (ggwave), with **QR** as an equal alternative | Unlike a static QR, sound cannot be shared over WhatsApp. Composing an existing library is preferred (CON-5) |
| D-2 | 2026-11-16 | **Audible sound by default**, ultrasound as an option | Real-phone tests: ultrasound reached only a very short range, audible went further. No free protocol above 20 kHz exists, and ggwave's ultrasound is still audible to many young people. The lecture pauses during check-in anyway (AS-2), so audible sound does not disturb |
| D-3 | 2026-11-13 | **Names only**, one name ↔ one phone, lecturer reset | The lecturer removed ID numbers from the roster (assignment Q&A). Known weakness: a student could claim a friend's name first. This is detected when the friend tries, and still requires being in the room |
| D-4 | 2026-11-16 | **No photo head count** for now (Won't) | The assignment gives it only as an example ("e.g."). Our methods identify *who* is present, while a photo tells only *how many*. Photos of students are also personal data (CON-1) |
| D-5 | 2026-11-16 | **No pulses, no check-out sound, no continuous listening** | Browsers cannot listen in the background. An always-open mic hurts privacy, and the lecturer warned against phones during class. The check-in window is a single moment chosen by the lecturer |
| D-6 | 2026-11-16 | **Late** is set manually by the lecturer | Simple and fair. The lecturer knows the context (e.g. a bus delay) |
| D-7 | 2026-11-16 | Attendance and participation are separate (FR-4.12) | Late or remote students should still be able to learn and ask questions |
| D-8 | 2026-11-16 | Anonymous forum posts are **fully anonymous**; the lecturer can delete them | Students are trusted adults (AS-1), and full anonymity encourages questions |
| D-9 | 2026-11-16 | Feature 4 = **teaching feedback for the lecturer**. A student summary is only Could | The lecturer described this tool in class as helping lecturers improve their teaching |
| D-10 | 2026-11-16 | Recording **upload only**, no Zoom URL | Zoom recordings require login, and the assignment says no Zoom integration is needed (CON-1) |
| D-11 | 2026-11-16 | AI provider is selectable: Claude, Gemini or OpenAI, behind an `LLMClient` interface | Different lecturers use different providers (Strategy pattern) |
| D-12 | 2026-11-16 | A single lecturer with a PIN | Enough for the demo; multiple accounts are Won't |
| D-13 | 2026-11-13 | Live updates by short polling every 2–3 s instead of WebSockets | Simpler and works through the HTTPS tunnel |
| D-14 | 2026-11-16 | The check-in window has **no automatic stop**; the lecturer ends it | The lecturer knows when everyone is seated; KISS |
| D-15 | 2026-11-16 | 2–3 well-known models per provider, from cheap/fast (free tier where available) to the strongest, plus a custom-ID field | Lecturers differ in budget; model names change often, so the list must be easy to update |

---

## 8. MoSCoW summary
| Priority | Requirements |
|---|---|
| **Must** | FR-1.1 · FR-2.1–2.3 · FR-3.1–3.4 · FR-4.1–4.12 · FR-5.1–5.3, 5.5, 5.7, 5.8 · FR-6.1–6.4 · FR-7.1, 7.1a, 7.2–7.6, 7.13, 7.14 |
| **Should** | FR-3.5 · FR-5.4, 5.6 · FR-6.5 · FR-7.7, 7.12, 7.15 |
| **Could** | FR-7.1b, 7.8, 7.9, 7.10 |
| **Won't (now)** | FR-1.2 multiple lecturers · FR-4.13 photo count · FR-4.14 pulses / check-out / continuous listening · FR-7.11 Zoom URL · Moodle integration |

**If time runs short,** these Must items move down to Should first, in this order: FR-7.1 with three providers (keep one), then FR-6.5 and FR-6.3 forum replies.

---

## 9. Open issues
- ~~**OI-1** Automatic stop of the check-in window?~~ **Resolved (D-14):** no automatic stop; the lecturer ends check-in.
- **OI-2** The sound must still be tested in the real lecture hall (back row, 2–3 phones). If it fails, QR becomes the recommended default (risk R-1 in the SoW). *The team will run this test.*
- ~~**OI-3** Which models to list per provider?~~ **Resolved (D-15)**, see FR-7.1a. Still open: the exact wording of the teaching-feedback prompt.
