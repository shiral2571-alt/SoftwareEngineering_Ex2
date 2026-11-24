# Class and Sequence Diagrams

Assignment To-Do #8: *"Define low-level class diagrams and sequence diagrams."*

**How to read this document:**
- **Part A** shows the whole system on one page, in plain words, for any reader.
- **Part B** is the **low-level** design the assignment asks for: the real classes and methods in `app/`, split into small diagrams.

---

# Part A — The big picture (no technical background needed)

### A1. What the system is made of
```mermaid
flowchart LR
    Lecturer([👩‍🏫 Lecturer]) --> Course[📚 Course<br/>with a list of students]
    Course --> Lecture[🗓 Lecture<br/>Draft · Open · Closed]
    Lecture --> Attendance[✅ Attendance<br/>Present · Late · Absent]
    Lecture --> Polls[📊 Polls]
    Lecture --> Forum[💬 Forum]
    Lecture --> Materials[📁 Materials<br/>and AI reports]
    Student([🧑‍🎓 Student + phone]) --> Attendance
    Student --> Polls
    Student --> Forum
```
A **course** has many **lectures**. Everything that happens in class (attendance, polls, questions, AI reports) belongs to a lecture.

### A2. How a student checks in (the main story)
```mermaid
sequenceDiagram
    actor S as 🧑‍🎓 Student's phone
    actor L as 👩‍🏫 Lecturer's laptop
    participant SV as 🖥 Server
    S->>S: 1. Tap "Get ready" (the phone listens)
    L->>S: 2. Laptop plays a short sound with a secret code
    S->>SV: 3. Phone sends the code it heard
    SV->>SV: 4. Is the code real and fresh (under 20 s)?
    SV-->>S: 5. ✅ "You're checked in" (the mic closes)
```
A friend at home cannot hear the sound, and a recording is useless after 20 seconds. The other way in is a QR code on the projector, which works the same way.

---

# Part B — Low-level design (classes and methods)

All the classes below are in `app/`. Each service receives the database (`db`), and services that deal with time also receive a `clock`. That is what makes them testable ([Testing strategy](TESTING_STRATEGY.md)).

### B1. Courses, students and phones
```mermaid
classDiagram
    direction LR
    class RosterSource {
        <<interface>>
        +load() list~Student~
    }
    class TableRosterSource {
        -header: list
        -rows: list
        +load() list~Student~
    }
    class CsvRosterSource
    class XlsxRosterSource
    RosterSource <|.. TableRosterSource
    TableRosterSource <|-- CsvRosterSource
    TableRosterSource <|-- XlsxRosterSource

    class Student {
        <<dataclass>>
        +student_id: str
        +name: str
    }
    class CourseService {
        -db: Connection
        -clock
        +create(name) int
        +all() list
        +get(course_id) dict
    }
    class CourseRoster {
        -db: Connection
        +import_into(course_id, source) int
        +students_of(course_id) list~Student~
        +is_enrolled(course_id, student_id) bool
        +find_by_name(name) Student
    }
    class DeviceRegistry {
        -db: Connection
        -roster: CourseRoster
        -clock
        +claim(student, device) ClaimResult
        +student_for(device) Student
        +reset(student_id)
    }
    class ClaimResult {
        <<dataclass>>
        +ok: bool
        +device_token: str
        +error: str
    }
    CourseRoster ..> RosterSource : reads from
    CourseRoster --> Student : manages
    DeviceRegistry --> CourseRoster : looks up
    DeviceRegistry ..> ClaimResult : returns
```
**Design note:** `RosterSource` is an interface. Today the list comes from a CSV or Excel file. A Moodle source could be added later without changing `CourseRoster` (Open/Closed principle).

### B2. Lectures and attendance
```mermaid
classDiagram
    direction LR
    class LectureService {
        -db: Connection
        -clock
        +create(course_id, title) int
        +open(lecture_id)
        +close(lecture_id)
        +reopen(lecture_id)
        -_move(lecture_id, new_state)
    }
    class MaterialService {
        -db: Connection
        -clock
        +add(lecture_id, kind, title, content, visible) int
        +of_lecture(lecture_id, students_only) list
    }
    class AttendanceService {
        -db: Connection
        -clock
        +open_window(lecture_id, channel) int
        +close_window(lecture_id)
        +issue_token(lecture_id) str
        +heard(student_id, token) HeardResult
        +set_status(lecture_id, student_id, status)
        +sheet(lecture_id, students) list
    }
    class HeardResult {
        <<dataclass>>
        +ok: bool
        +message: str
    }
    class Database {
        <<SQLite>>
        lectures
        checkin_windows
        tokens
        attendance
        materials
    }
    LectureService --> Database : writes lectures.state
    MaterialService --> Database : materials
    AttendanceService --> Database : windows, tokens, attendance
    AttendanceService ..> Database : reads lectures.state directly
    AttendanceService ..> HeardResult : returns
```
**Design note:** the two services are **not** linked in code. `AttendanceService` reads the lecture's state straight from the shared `lectures` table, so it opens a check-in window only in an **open** lecture. This keeps the services independent, at the cost of both knowing the table. `LectureService.close()` also ends any open check-in window.

**The lecture's states:**
```mermaid
stateDiagram-v2
    [*] --> Draft : create
    Draft --> Open : open
    Open --> Closed : close
    Closed --> Open : reopen
```
Any other move, for example closing a draft, is refused (`LectureStateError`).

### B3. Polls and forum
```mermaid
classDiagram
    direction LR
    class PollService {
        -db: Connection
        -clock
        +create(lecture_id, title, questions, show_correct) int
        +launch(poll_id)
        +close(poll_id)
        +answer(question_id, student_id, option, text) bool
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
    class ForumService {
        -db: Connection
        -clock
        +post(lecture_id, student_id, text, anonymous) int
        +reply(post_id, text) int
        +toggle_upvote(post_id, student_id) bool
        +delete_post(post_id)
    }
    PollService "1" --> "*" Question : contains
```
`kind` is *quiz* (with a correct answer), *choice* or *text*. An anonymous post stores **no** student at all.

### B3b. Homework (feature 5)
```mermaid
classDiagram
    direction LR
    class AssignmentService {
        -db: Connection
        -clock
        +create(course_id, title, instructions, deadline) int
        +submit(assignment_id, student_id, filename, text)
        +my_submission(assignment_id, student_id) dict
        +peers(assignment_id, student_id) list
        +save_review(assignment_id, student_id, review, engine)
    }
    class TextFiles {
        <<module>>
        +extract_text(filename, data) str
    }
    class StudentReview {
        <<function>>
        +review_submission(assignment, work, peers, llm)
    }
    AssignmentService ..> TextFiles : uploads read by
    StudentReview ..> AssignmentService : peers from
```
`peers()` returns at most **5** recent submissions, as text only, without names. The review prompt forbids revealing them.

### B4. AI providers (Strategy pattern) and settings
```mermaid
classDiagram
    direction TB
    class LLMClient {
        <<abstract>>
        +provider: str
        +model: str
        -api_key: str
        +complete(system, prompt) str
    }
    class ClaudeClient
    class GeminiClient
    class OpenAIClient
    class OfflineClient
    LLMClient <|-- ClaudeClient
    LLMClient <|-- GeminiClient
    LLMClient <|-- OpenAIClient
    LLMClient <|-- OfflineClient

    class LLMSettings {
        -db: Connection
        +save(provider, model, key)
        +public_view() dict
        +client() LLMClient
    }
    class AppSettings {
        -db: Connection
        +public_url() str
        +set_public_url(url) str
    }
    class TeachingFeedback {
        <<function>>
        +teaching_feedback(transcript, llm)
    }
    class ExcelExporter {
        +build(course_id) bytes
    }
    LLMSettings ..> LLMClient : creates the chosen one
    TeachingFeedback ..> LLMClient : uses only the interface
```
**Why this matters:** the teaching-feedback code talks only to `LLMClient`. Adding Gemini and OpenAI next to Claude did not change it at all. `OfflineClient` is used when there is no key, so nothing crashes. `AppSettings` keeps the public phone address used by every QR code, and `ExcelExporter` builds the offline spreadsheet from the other services.

---

### B5. Sequence: sound check-in (low level)
```mermaid
sequenceDiagram
    participant P as Phone
    participant L as Laptop
    participant API as Flask routes
    participant ATT as AttendanceService

    P->>P: listen() — mic on
    L->>API: start check-in (sound)
    API->>ATT: open_window()
    loop every 10 s
        L->>API: new code
        API->>ATT: issue_token() — valid 20 s
        L-)P: play code as sound
    end
    P->>API: POST /api/heard {code}
    API->>ATT: heard(student, code)
    ATT-->>API: Checked in
    API-->>P: ok
    P->>P: stop() — mic off
```

### B6. Sequence: teaching feedback (low level)
```mermaid
sequenceDiagram
    participant UI as Lecturer page
    participant API as Flask routes
    participant TF as teaching_feedback
    participant C as LLMClient (e.g. Gemini)

    UI->>API: upload transcript
    API->>TF: teaching_feedback(transcript, client)
    TF->>TF: measure words, filler words, pace
    alt AI key configured
        TF->>C: complete(our prompt, transcript)
        C-->>TF: report in Hebrew
    else no key or no internet
        TF->>TF: statistics only
    end
    TF-->>API: report, with "Model: …" on top
    API-->>UI: show it and save it in Materials
```

### B7. Sequence: a student submits homework (low level)
```mermaid
sequenceDiagram
    participant P as Student phone
    participant API as Flask routes
    participant HW as AssignmentService
    participant R as review_submission
    participant C as LLMClient

    P->>API: upload essay.docx
    API->>API: extract_text() → plain text
    API->>HW: submit() — replaces any earlier one
    API->>HW: peers() — 5 recent, no names
    API->>R: review(assignment, work, peers)
    R->>C: complete(student prompt, …)
    C-->>R: review in Hebrew
    R-->>API: review with "Model: …"
    API->>HW: save_review()
    API-->>P: review + latest submission date
```

> **More detail:** every method is in the code (`app/*.py`), and each one is covered by a test listed in the [Testing strategy](TESTING_STRATEGY.md).
