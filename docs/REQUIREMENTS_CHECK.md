# Requirements check

> **Historical snapshot (2026-11-13).** This was the gap analysis that started the redesign. Every gap listed here was resolved or decided later; the final status is in [SRS.md](SRS.md) (status column and decision log) and [SOW.md §6](SOW.md).

Status as of 2026-11-13. Sources:
- **Assignment document:** I2SE_Exe2, including its Q&A.
- **Q&A links:** the Ex1 repository list for feature 5, and Zoom's automatic summary of the class where the lecturer explained Ex2.

## What the lecturer said in class (from the Zoom summary)
The summary is machine-generated and Zoom's quality is "nothing to write home about", so treat it as a hint, not a quote.
- **Simplicity over technology.** The lecturer warned against complex solutions and named face recognition as an example. He used Dropbox to show the value of a simple product.
- **Attendance.** He described a basic photo-based approach in which the professor checks the photos manually. He asked teams to handle **edge cases**, such as a gap between registered and actual attendance.
- **The SoW must cover a "Happy Case" and "Edge Cases"** for student registration and attendance.
- **Comments:** keep them simple. **Polls:** quick and easy. He warned against **wasting class time on phones**.
- **Feature 4 is a tool that helps the *lecturer* teach better.** It gives quick insights and statistics from the video or transcript, for example language mistakes, stuttering and audio quality. Reports must be **short**, because long ones are not read.
- **Feature 5** reviews student submissions automatically. It will be tested on the **Ex1 GitHub repositories**: about 54 links in a form-responses sheet.
- Everything should be simple enough for high-school students to build and use, and it must be demoable.

## Features
| # | Requirement | Status | Gap / action |
|---|---|---|---|
| 1 | Automatic attendance; the lecturer evaluates it simply; online/offline sheet | ✅ Sound + rotating QR + manual, live sheet, Excel | The photo count is only an example ("e.g."). We decided not to do it for now (CONCEPT §10) and must justify that. **Pitch the sound as KISS:** one tap for the student, one button for the lecturer. Add edge cases to the SoW |
| 2 | Comments and suggestions, real time / offline | ✅ | — |
| 3 | KISS polls | ✅ | — |
| 4 | ML summary of the class video (Zoom/Meet/Classroom) | ⚠️ Content summary of the transcript | **Mismatch:** the lecturer wants *teaching feedback*, such as speaking pace, filler words, long monologues and audio quality, in a short report |
| 5 | Deep LLM review of homework + comparison to other students | ⚠️ Works on uploaded files | **Mismatch:** the test data is a list of GitHub repository links, so the tool should accept repository URLs |

## Requirements and guidelines
| Requirement | Status | Note |
|---|---|---|
| Works in *this* class (real demo) | ⚠️ | The room is a large lecture hall. Audible sound worked at short range in a small room, so the hall still has to be tested. The QR fallback covers a failure |
| KISS smartphone web app | ✅ | — |
| No Moodle, Zoom or personal data | ✅ | Names only; the roster is a CSV file |
| Design only what can be implemented | ✅ | Background listening is listed as a limitation, not promised |
| Pulses vs. "don't waste class time on phones" | ⚠️ | Pulses need the page open. Answer: the phone can lie on the desk with the screen on, and no interaction is needed |

## To-Do (12 items)
| # | Item | Status |
|---|---|---|
| 1 | Repository + README (problem, scope) | ✅ |
| 2 | Submit the repository link through the course form | ❌ At the end |
| 3 | Tools report, tested in real life | ⚠️ Data exists, not written |
| 4 | SoW (include happy case + edge cases) | ❌ |
| 5 | SRS | ❌ |
| 6 | Main use cases (client stories) | ❌ |
| 7 | Main software components | ❌ |
| 8 | Low-level class diagrams + sequence diagrams | ❌ |
| 9 | Testing strategy covering the classes | ⚠️ 34 tests, document not written |
| 10 | Demo web app (vibe code vs. find and compose) | ✅ Explain what is composed (ggwave, Claude, Flask) and what is ours |
| 11 | Demo in class | ⏳ Rehearse with several phones |
| 12 | Conclusions | ❌ |

**Deadline: 2026-11-25.**
