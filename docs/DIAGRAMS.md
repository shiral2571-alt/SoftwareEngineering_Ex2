# Class and Sequence Diagrams

Assignment To-Do #8: *"Define low-level class diagrams and sequence diagrams."*
The diagrams are written in Mermaid, which GitHub renders as images. They match the code in `app/`. Method signatures are simplified, and `db` is the SQLite connection passed into every service.

---

## 1. Class diagram: domain services

```mermaid
classDiagram
    direction LR

    class CourseService {
        -db
        -clock
        +create(name) int
        +all() list~dict~
        +get(course_id) dict
    }
    class CourseRoster {
        -db
        +import_into(course_id, source: RosterSource) int
        +students_of(course_id) list~Student~
        +is_enrolled(course_id, student_id) bool
        +courses_of(student_id) list~int~
        +find_by_name(name) Student
        +get(student_id) Student
    }
    class Student {
        <<dataclass>>
        +student_id: str
        +name: str
    }
    class RosterSource {
        <<interface>>
        +load() list~Student~
    }
    class TableRosterSource {
        -header
        -rows
        +load() list~Student~
    }
    class CsvRosterSource
    class XlsxRosterSource
    RosterSource <|.. TableRosterSource
    TableRosterSource <|-- CsvRosterSource
    TableRosterSource <|-- XlsxRosterSource
    CourseRoster ..> RosterSource : uses
    CourseRoster ..> Student : returns

    class DeviceRegistry {
        -db
        -roster: CourseRoster
        +claim(student, current_device) ClaimResult
        +student_for(device_token) Student
        +is_registered(student_id) bool
        +reset(student_id)
    }
    class ClaimResult {
        <<dataclass>>
        +ok: bool
        +device_token: str
        +error: str
    }
    DeviceRegistry --> CourseRoster
    DeviceRegistry ..> ClaimResult

    class LectureService {
        -db
        -clock
        +create(course_id, title) int
        +open(lecture_id)
        +close(lecture_id)
        +reopen(lecture_id)
        +rename(lecture_id, title)
        +of_course(course_id) list
        +visible_to_student(course_ids) list
        -_move(lecture_id, new_state)
    }
    class MaterialService {
        +add(lecture_id, kind, title, content, visible) int
        +of_lecture(lecture_id, students_only) list
        +delete(material_id)
    }
    class AttendanceService {
        -db
        -clock
        +open_window(lecture_id, channel) int
        +close_window(lecture_id)
        +open_window_of(lecture_id) dict
        +issue_token(lecture_id) str
        +heard(student_id, token) HeardResult
        +set_status(lecture_id, student_id, status)
        +status_of(lecture_id, student_id) str
        +sheet(lecture_id, students) list
    }
    class HeardResult {
        <<dataclass>>
        +ok: bool
        +message: str
    }
    AttendanceService ..> HeardResult

    class PollService {
        -db
        -clock
        +create(lecture_id, title, questions, show_correct) int
        +launch(poll_id)
        +close(poll_id)
        +answer(question_id, student_id, option_index, text) bool
        +of_lecture(lecture_id) list
        +for_student(lecture_id, student_id) list
    }
    class Question {
        <<dataclass>>
        +text: str
        +kind: str
        +options: list
        +correct: int
        +validate() Question
    }
    PollService ..> Question

    class ForumService {
        -db
        -clock
        +post(lecture_id, student_id, text, anonymous) int
        +reply(post_id, text) int
        +delete_post(post_id)
        +toggle_upvote(post_id, student_id) bool
        +of_lecture(lecture_id, viewer_id) list
    }
```

## 2. Class diagram: AI gateway (Strategy pattern)

```mermaid
classDiagram
    direction LR
    class LLMClient {
        <<abstract>>
        +provider: str
        +model: str
        -api_key: str
        +name: str
        +complete(system, prompt)* str
    }
    class ClaudeClient {
        +complete(system, prompt) str
    }
    class GeminiClient {
        +complete(system, prompt) str
    }
    class OpenAIClient {
        +complete(system, prompt) str
    }
    class OfflineClient {
        +complete(system, prompt) str
    }
    LLMClient <|-- ClaudeClient
    LLMClient <|-- GeminiClient
    LLMClient <|-- OpenAIClient
    LLMClient <|-- OfflineClient

    class LLMSettings {
        -db
        +save(provider, model, api_key)
        +public_view() dict
        +client() LLMClient
        +clear_key()
    }
    LLMSettings ..> LLMClient : creates

    class ai_tools {
        <<module>>
        +TEACHING_FEEDBACK_PROMPT
        +teaching_feedback(transcript, llm) dict
        +student_summary(transcript, llm) dict
        +review_homework(submissions, assignment, llm) dict
        +speaking_stats(text, cues) dict
        +similarity_matrix(submissions) list
    }
    ai_tools ..> LLMClient : depends only on the interface

    class ExcelExporter {
        +build(course_id) bytes
    }
```
**Why Strategy:** `teaching_feedback()` only calls `llm.complete()`. Adding Gemini and OpenAI next to Claude did not change a single line of the AI features (Open/Closed). `OfflineClient` is the *Null Object*: without a key, the features take their offline path instead of crashing.

## 3. State diagram: the lecture as an object

```mermaid
stateDiagram-v2
    [*] --> Draft : create()
    Draft --> Open : open()
    Open --> Closed : close() and end check-in
    Closed --> Open : reopen()
    note right of Draft
        Only the lecturer sees it. Polls and materials can be prepared.
    end note
    note right of Open
        Students see it. Check-in windows can be opened.
    end note
    note right of Closed
        Still editable: attendance, polls, forum, materials.
    end note
```
Any other transition, for example closing a draft, raises `LectureStateError`. The allowed moves are one table in the code (`TRANSITIONS` in `lectures.py`).

---

## 4. Sequence diagram: sound check-in with "Get ready" (UC-4, main flow)

```mermaid
sequenceDiagram
    actor S as Student
    participant P as Phone (student.html + sound.js)
    participant L as Lecturer laptop (lecturer.html + sound.js)
    participant API as Flask routes
    participant ATT as AttendanceService
    participant DB as SQLite

    S->>P: tap "Get ready to check in"
    P->>P: Sound.listen(onToken) — mic opens (max 2 min)
    Note over L: Lecturer presses "Start check-in (sound)"
    L->>API: POST /api/l/lectures/{id}/checkin {start, sound}
    API->>ATT: open_window(lecture, "sound")
    ATT->>DB: INSERT checkin_windows
    loop every ~10 s while the window is open
        L->>API: POST /api/l/lectures/{id}/token
        API->>ATT: issue_token(lecture)
        ATT->>DB: INSERT tokens (expires in 20 s)
        API-->>L: {token: "M6ADT6"}
        L-)P: plays the token as sound (ggwave)
    end
    P->>P: ggwave.decode → "M6ADT6" (shape check)
    P->>API: POST /api/heard {token}  + device cookie
    API->>API: DeviceRegistry.student_for(cookie) → student
    API->>ATT: heard(student, token)
    ATT->>DB: token known? window open? not expired? enrolled?
    ATT->>DB: UPSERT attendance = present (method: sound)
    ATT-->>API: HeardResult(ok, "Checked in")
    API-->>P: {ok: true}
    P->>P: stop() — mic closed
    P-->>S: "✅ You're checked in"
    Note over L: Lecturer presses "End check-in" → close_window()
```

## 5. Sequence diagram: QR check-in for a student not yet registered (UC-4a + UC-3)

```mermaid
sequenceDiagram
    actor S as Student
    participant P as Phone camera / browser
    participant API as Flask routes
    participant ATT as AttendanceService
    participant ID as DeviceRegistry

    Note over S,P: Projector shows a rotating QR → https://…/j/K7Q3XH
    S->>P: scan the QR
    P->>API: GET /j/K7Q3XH
    API->>ID: student_for(cookie) → none
    API->>API: session.pending_token = K7Q3XH
    API-->>P: redirect to / (registration)
    S->>P: pick own name, confirm
    P->>API: POST /api/register {name}
    API->>ID: claim(student, current_device)
    ID-->>API: ClaimResult(ok, device_token)
    API->>ATT: heard(student, pending_token)
    ATT-->>API: HeardResult(ok, "Checked in")
    API-->>P: Set-Cookie: device (HttpOnly) → status Present
```

## 6. Sequence diagram: teaching feedback (UC-10)

```mermaid
sequenceDiagram
    actor L as Lecturer
    participant UI as lecturer.html
    participant API as Flask routes
    participant AI as ai_tools.teaching_feedback
    participant S as LLMSettings
    participant C as LLMClient (e.g. GeminiClient)
    participant M as MaterialService

    L->>UI: upload / paste transcript, "Get teaching feedback"
    UI->>API: POST /api/l/lectures/{id}/feedback
    API->>S: client()
    S-->>API: GeminiClient(model, key) — or OfflineClient
    API->>AI: teaching_feedback(transcript, client)
    AI->>AI: parse_transcript → text + cues
    AI->>AI: speaking_stats → words, fillers, pace (if timings)
    alt a provider is configured and reachable
        AI->>C: complete(TEACHING_FEEDBACK_PROMPT, stats + transcript)
        C-->>AI: Hebrew report (5 sections)
    else no key / error
        AI->>AI: measured statistics only + note
    end
    AI-->>API: {engine, report starting with "Model: …"}
    API->>M: add(lecture, "report", "Teaching feedback (lecturer only)", report, visible=false)
    API-->>UI: report → shown and saved in Materials
```

## 7. Sequence diagram: poll prepared in advance (UC-6, UC-7)

```mermaid
sequenceDiagram
    actor L as Lecturer
    actor S as Student
    participant API as Flask routes
    participant PS as PollService

    L->>API: POST /api/l/lectures/{draft}/polls {questions}
    API->>PS: create(…) — each Question.validate()
    Note over L: In class: open the lecture, press "Launch"
    L->>API: POST /api/l/polls/{id} {launch}
    S->>API: GET /api/lecture/{id} (every 3 s)
    API->>PS: for_student(lecture, student)
    API-->>S: live poll (no results, no answers)
    S->>API: POST /api/answer {question, option}
    API->>PS: answer(…) — once per student per question
    L->>API: GET /api/l/lectures/{id} (every 2.5 s)
    API->>PS: of_lecture(lecture) → counts, % correct
```
