# Conclusions

Assignment To-Do #12: *"Conclude the assignment; write down a short description of the results."*

## What we built
A KISS smartphone web app for teaching in class, organised around **the lecture as an object**: Draft → Open → Closed, editable afterwards. It covers all five assignment features:

1. **Attendance (main feature).** A check-in window opened by the lecturer: the laptop plays a short-lived code as **sound**, or shows a **rotating QR**. Students check in with one tap, and their microphone closes right after. There is a live sheet with Present / Late / Absent, and an Excel export.
2. **Forum** per lecture: named or fully anonymous posts, lecturer replies, 👍.
3. **KISS polls:** sets of questions prepared in advance or imported from a template; quizzes show % correct.
4. **Teaching feedback** from the class transcript, written in Hebrew, including the lecturer's commitments to students as tasks.
5. **Homework review** with a deterministic similarity table plus LLM comments.

It is backed by 49 automated tests and a full set of design documents (SoW, SRS with 18 decisions, use cases, components, class, sequence and state diagrams, testing strategy, tools report).

## Results
| Goal | Result |
|---|---|
| Attendance that can't be shared on WhatsApp | ✅ Codes live 20–30 s, and only while the lecturer keeps check-in open. Recordings and photos sent later are rejected (tested) |
| One-tap check-in on a real phone | ✅ With *get ready early*, the phone checked in on the first broadcast, and the mic closed |
| Quiet (ultrasound) check-in | ❌ Unreliable with laptop speakers: very short range, then not received. **Audible is the default**, since the lecture pauses for check-in anyway |
| Works in the real large lecture hall | ⏳ To be confirmed in the hall test; the QR path is the fallback |
| LLM-ready teaching tools | ✅ A real lecture transcript with Gemini gave a structured, honest report, in Hebrew after a prompt fix |
| KISS | ✅ No installation, no typing after registration, names only |

## What we learned
1. **Test the risky tool first, on real devices.** A one-day sound spike on a real phone shaped the whole design. Ultrasound looked perfect on paper and failed in practice, and audible sound plus a rotating QR made the system robust.
2. **Requirements hide in more than the written spec.** The assignment said "ML summary of class video". Only the lecturer's explanation in class showed that he meant *feedback for the lecturer*. The Q&A also changed our identity design, because ID numbers were removed. Reading every source of requirements is part of engineering.
3. **Small real tests find real bugs.** A missed first sound, materials collapsing every 3 seconds on the phone, an AI answering in the wrong language, and a copied transcript holding only a third of the lecture were all found by trying the system with real people and data. None of them showed up in unit tests.
4. **Interfaces paid off.** Because the AI features depend only on `LLMClient`, adding Gemini and OpenAI did not touch the feature code. Fixing time with an injected clock made expiry rules testable in milliseconds.
5. **"Design everything, implement what matters."** MoSCoW let us cut homework review from GitHub links, video upload and a photo head count without losing the core. They are documented as *Won't (now)* with reasons.
6. **Vibe coding needs a driver.** An AI assistant wrote most of the code quickly, but the decisions, the real-life tests and the corrections came from the team. The most valuable outputs were the decision log and the test results, not the lines of code.

## Limitations
- **Not yet verified in the large hall.** Sound range there is unknown, and the QR is the fallback.
- **A live relay** of the sound or the QR to a friend at home within 20 s (E13) is possible. It is an accepted risk, and the lecturer compares the counter with the room.
- **Names-only identity:** someone could claim a friend's name first. This is detected when the friend tries, and the lecturer resets it.
- **The server runs on the lecturer's laptop.** The forum and materials are unavailable when the laptop is off.
- **Teaching-feedback quality depends on the transcript.** Speakers are often unlabelled, and copying from Zoom can lose text.

## Future work
- Host the server in the cloud, so the forum and materials work after class.
- Integrate with Moodle (roster import) and Zoom (transcript download), which were out of scope here.
- Homework review directly from a list of GitHub repositories, as in the lecturer's Ex1 list.
- Speech-to-text for video upload (OpenAI or Gemini).
- An optional photo head count as a sanity check next to the check-in counter.
- A native app wrapper to allow background presence checks, which browsers cannot do.
