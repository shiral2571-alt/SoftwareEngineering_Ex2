# Ex2 — One-Week Schedule

Working deadline: **Sunday 2026-11-15** (submission "in one week" from 2026-11-08; confirm the exact date and the class-demo date).
Numbers in brackets refer to the assignment's To-Do list.

| Day | Date | Work | To-Do | Done when |
|---|---|---|---|---|
| Sun | 11-08 | Technical spike (done); ultrasound test at 1 m; create repo + README | 1, 2 | Repo exists; README states problem and scope |
| Mon | 11-09 | Distance / noise / second-phone tests; get student list from Drive; Tools Report | 2 | CSV of results in repo; every proposed tool has a recorded test |
| Tue | 11-10 | SoW; SRS; use cases | 3, 4, 5 | Requirements numbered and measurable |
| Wed | 11-11 | Components; class + sequence diagrams; testing strategy | 6, 7, 8 | Every class in the diagrams is covered by the test strategy |
| Thu | 11-12 | Build core: check-in by sound, QR fallback, live attendance sheet, Excel export, pulses | 9 | Attendance works end to end on a real phone |
| Fri | 11-13 | Polls, comments, LLM features (minimal), server load script | 9 | All 5 features demonstrable; load script passes |
| Sat | 11-14 | Full rehearsal with 3–5 real phones; fixes; conclusions | 10, 11 | 10-minute demo script run start to finish |
| Sun | 11-15 | Buffer, final check, submit | 10, 11 | Submitted |

## If time runs short (cut in this order)
1. Video summary works from an uploaded **transcript** only (no speech-to-text).
2. Homework review runs on a small sample of submissions.
3. Comments stay a plain stored feed.

Attendance (the main feature) and its QR fallback are never cut.

## Testing "40 phones" without 40 phones
The risk splits into two independent questions:

| Question | How we test it |
|---|---|
| Does the **server** survive ~40 simultaneous check-ins? | A script simulates 40+ concurrent clients. No phones needed. |
| Does the **sound** reach every seat? | 3–5 real phones placed at front / middle / back / side of the room. Sound is a broadcast, so one phone hearing it does not reduce what another phone hears. |

The first real 40-phone run is the class demo itself, which is why the QR fallback must be ready.
