# Testing Strategy

Assignment To-Do #9: *"Define a testing strategy; make sure to address the classes (as in 7)."*
The classes are those in [COMPONENTS.md](COMPONENTS.md) and [DIAGRAMS.md](DIAGRAMS.md). Requirements are referenced by their SRS IDs ([SRS](SRS.md)).

## 1. Goals
1. Every **domain class** has automated tests for its rules: the happy path, plus the edge cases from the SoW (E1–E13).
2. **Security and privacy promises are tested, not assumed.** The API key is never returned, anonymous posts store no name, and expired codes are rejected.
3. **Whatever cannot be automated is tested in real life.** This covers sound through air, real phones, the lecture hall and real AI models. The results are recorded in the [Tools report](TOOLS_REPORT.md).
4. Tests are fast (about 4 s), so they run before every commit.

## 2. Test levels
| Level | What | How | Where |
|---|---|---|---|
| **Unit** | One service class with its rules | `pytest`; an in-memory SQLite database (`:memory:`); an injected **FakeClock** for anything time-based | `tests/test_services.py` (35 tests) |
| **Integration (API)** | A full flow through HTTP, the same calls the phone and dashboard make | Flask `test_client()`, a temporary database file, a fake LLM | `tests/test_routes.py` (14 tests) |
| **Manual, in real life** | Sound between devices, phone browsers, mic permission, QR scan, the large hall, real AI output | Checklists with recorded results | [TOOLS_REPORT.md](TOOLS_REPORT.md), [CONCEPT.md §8](CONCEPT.md) |
| **Demo rehearsal** | The whole 10-minute script with 3–5 phones | The README demo script | Before the class demo |

**Design choices that make the classes testable:**
- **Injected clock.** Every service takes `clock=time.time`, and tests pass a `FakeClock` that can `advance(21)` seconds. So "a recording replayed after 20 s is rejected" is tested in milliseconds, without waiting.
- **Injected database.** Services receive a connection, so tests use a fresh in-memory database each time.
- **The LLM sits behind an interface.** Tests inject an `OfflineClient`, a failing `BrokenLLM` and an `EchoLLM`. No test calls a paid API, and no test depends on the network.
- **Thin routes.** The logic lives in services, so most behaviour is covered by fast unit tests.

## 3. Coverage per class
| Class (component) | What is tested | Tests | SRS / edge cases |
|---|---|---|---|
| `CsvRosterSource`, `XlsxRosterSource`, `TableRosterSource` (C6) | Names only; first + last name; Hebrew headers; optional ID; BOM; a missing name column and duplicates are rejected; stable keys on re-import | `test_names_only_csv_gets_stable_keys`, `test_csv_first_last_and_optional_id`, `test_xlsx_roster`, `test_roster_rejects_missing_name_column_and_duplicates` | FR-2.2, FR-2.3, E12 |
| `CourseService`, `CourseRoster` (C6) | Separate rosters per course; one person in two courses; name lookup ignores case and spaces | `test_courses_have_separate_rosters`, `test_first_phone_owns_the_name` | FR-2.1 |
| `DeviceRegistry` (C7) | The first phone owns a name; the same phone again is fine; another phone is refused; reset frees the name; switching names releases the old one | `test_first_phone_owns_the_name`, `test_switching_name_releases_the_old_one`, `test_second_phone_cannot_take_a_registered_name`, `test_phone_cannot_switch_student_after_check_in` | FR-4.1, 4.2, 4.9, E4, E5, E6 |
| `LectureService` (C8) | Draft → Open → Closed → Reopen; illegal transitions raise errors; drafts are hidden from students; closing ends check-in | `test_lecture_lifecycle_and_reopen`, `test_students_never_see_drafts`, `test_closing_ends_the_checkin_window`, `test_drafts_are_hidden_from_students`, `test_lifecycle_errors_are_reported` | FR-3.1–3.4, E9 |
| `MaterialService` (C8) | Teaching feedback is saved as lecturer-only and is invisible to students | `test_feedback_is_saved_as_private_material` | FR-3.5, FR-7.12 |
| `AttendanceService` (C9) | Tokens only while a window is open, and only in an open lecture; token format; once per student; **expiry after 20 s**; rejected after the lecturer ends check-in; another course's student rejected; unknown or lowercase tokens; QR method; manual Late, also after close; Absent by default | `test_tokens_only_while_a_window_is_open`, `test_window_needs_an_open_lecture`, `test_valid_token_checks_in_once`, `test_expired_token_is_rejected`, `test_token_after_the_lecturer_ended_checkin_is_rejected`, `test_student_from_another_course_cannot_check_in`, `test_unknown_token_and_lowercase`, `test_lecturer_sets_late_and_can_edit_after_close`, `test_attendance_sheet_defaults_to_absent`, `test_full_sound_check_in_flow`, `test_qr_scan_before_registering`, `test_manual_late_status` | FR-4.3–4.8, 4.10, NFR-7, E2, E3 |
| `PollService`, `Question` (C10) | Quiz, choice and text in one poll; one answer each; % correct; validation; drafts and closed polls can't be answered; correct answer shown only if allowed and answered; template round trip; bad row reported | `test_poll_with_several_question_kinds`, `test_quiz_validation`, `test_draft_and_closed_polls_cannot_be_answered`, `test_correct_answer_shown_only_if_allowed_and_answered`, `test_poll_import_template_round_trip`, `test_poll_import_reports_the_bad_row`, `test_poll_prepared_in_draft_then_answered` | FR-5.1–5.8 |
| `ForumService` (C11) | **Anonymous stores NULL** (checked in the database); replies; 👍 toggle; most-voted first; delete; an absent student can still post | `test_forum_anonymous_is_fully_anonymous`, `test_forum_reply_upvote_order_and_delete`, `test_forum_round_trip`, `test_absent_student_can_still_participate` | FR-6.1–6.5, FR-4.12, NFR-5, E8, E11 |
| `LLMSettings`, `LLMClient` subclasses (C12) | **The key is never returned** (service and HTTP); masked; an empty field keeps the key; switching provider drops the key; unknown provider rejected | `test_api_key_is_never_returned`, `test_settings_never_expose_the_key` | FR-7.1–7.3, NFR-6 |
| `ai_tools` (C13) | Transcript parsing (VTT timings); pace, filler words and questions; offline report; **the model name is shown**; **Hebrew requested**; fallback when the provider fails; similarity ignores comments; extractive summary | `test_transcript_parsing_and_stats`, `test_teaching_feedback_offline_and_empty`, `test_teaching_feedback_names_the_model_and_asks_for_hebrew`, `test_ai_falls_back_when_the_provider_fails`, `test_similarity_ignores_comments_and_whitespace`, `test_extractive_summary_keeps_order_and_limit` | FR-7.4–7.7, 7.6a, 7.6b, 7.13, 7.14, E10 |
| `ExcelExporter` (C14) | Sheet names; drafts excluded; Present and Late in the overview; a valid xlsx download | `test_excel_export`, `test_excel_download` | FR-4.11 |
| Web API (C5) | The lecturer PIN is required; wrong PIN refused | `test_lecturer_api_requires_pin` | FR-1.1, NFR-6 |

## 4. What is not automated, and how it is covered
| Area | Why not automated | Real-life test |
|---|---|---|
| `sound.js`, ggwave over the air | Needs a speaker, air and a microphone | Real phone tests: audible ✅, ultrasound ❌, *get ready early* ✅; **real auditorium, back row: audible ✅, ultrasound ❌** (empty hall) |
| Mic opening and closing on iOS/Android | Browser permission UI | Real phone: the mic indicator disappears after check-in ✅ |
| QR scan with a phone camera | Needs a camera | Demo rehearsal |
| Real LLM output quality | Paid, non-deterministic | Gemini 3.5 Flash-Lite on a real lecture transcript ✅ (structure, honesty, Hebrew after D-18) |
| Page refresh behaviour (polling) | UI timing | Found by a real phone test: materials closed every 3 s. Fixed and re-checked in the browser |
| Load: 40 phones at once | Needs many devices | Partly: each check-in is one small request; rehearse with 3–5 phones (risk noted in the SoW) |

## 5. How to run
```bash
py -m pytest -q
```
The expected result is **49 passed** in about 4 seconds. No network, API key or browser is needed.

## 6. Rules
- **Every bug found in real life gets a test, where possible.** Example: the Hebrew-output fix added `test_teaching_feedback_names_the_model_and_asks_for_hebrew`.
- **Test names describe the rule** and are grouped by SRS requirement, so a failing test points straight to the broken requirement.
- **No test may call a real AI provider or the internet.**
- **Run the full suite before every commit.** All commits in this project were made with the suite passing.
