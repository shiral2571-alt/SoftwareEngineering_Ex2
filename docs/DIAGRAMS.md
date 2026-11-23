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
    class CsvRosterSource
    class XlsxRosterSource
    RosterSource <|.. CsvRosterSource
    RosterSource <|.. XlsxRosterSource

    class Student {
        +student_id: str
        +name: str
    }
    class CourseRoster {
        +import_into(course_id, source)
        +students_of(course_id) list
        +find_by_name(name) Student
    }
    class DeviceRegistry {
        +claim(student, device) ClaimResult
        +student_for(device) Student
        +reset(student_id)
    }
    CourseRoster ..> RosterSource : reads from
    CourseRoster --> Student : manages
    DeviceRegistry --> CourseRoster : looks up
```
**Design note:** `RosterSource` is an interface. Today the list comes from a CSV or Excel file; a Moodle source could be added later without changing `CourseRoster` (Open/Closed principle).

### B2. Lectures and attendance
```mermaid
classDiagram
    direction LR
    class LectureService {
        +create(course_id, title) int
        +open(lecture_id)
        +close(lecture_id)
        +reopen(lecture_id)
    }
    class AttendanceService {
        +open_window(lecture_id, channel)
        +close_window(lecture_id)
        +issue_token(lecture_id) str
        +heard(student_id, token) HeardResult
        +set_status(lecture_id, student_id, status)
    }
    class HeardResult {
        +ok: bool
        +message: str
    }
    LectureService <.. AttendanceService : check-in only in an open lecture
    AttendanceService ..> HeardResult : returns
```

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
        +create(lecture_id, title, questions)
        +launch(poll_id)
        +answer(question_id, student_id, choice)
    }
    class Question {
        +text: str
        +kind: str
        +options: list
        +correct: int
        +validate()
    }
    class ForumService {
        +post(lecture_id, student_id, text, anonymous)
        +reply(post_id, text)
        +toggle_upvote(post_id, student_id)
    }
    PollService "1" --> "*" Question : contains
```
`kind` is *quiz* (with a correct answer), *choice* or *text*. An anonymous post stores **no** student at all.

### B4. AI providers (Strategy pattern)
```mermaid
classDiagram
    direction TB
    class LLMClient {
        <<abstract>>
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
        +save(provider, model, key)
        +client() LLMClient
    }
    class TeachingFeedback {
        <<function>>
        +teaching_feedback(transcript, llm)
    }
    LLMSettings ..> LLMClient : creates the chosen one
    TeachingFeedback ..> LLMClient : uses only the interface
```
**Why this matters:** the teaching-feedback code talks only to `LLMClient`. Adding Gemini and OpenAI next to Claude did not change it at all. `OfflineClient` is used when there is no key, so nothing crashes.

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

> **More detail:** every method is in the code (`app/*.py`), and each one is covered by a test listed in the [Testing strategy](TESTING_STRATEGY.md).
