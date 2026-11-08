# Core Concept — Acoustic & Continuous Attendance

> Ex2 – Introduction to Software Engineering (OOP/OOD): Web-based Teaching Tool
> Status: **agreed concept** (2026-11-08). This file is the single source of truth for the core idea;
> all later documents (README, SRS, SoW, diagrams) must stay consistent with it.

## 1. The problem with "obvious" attendance
Most solutions use a static QR code or a short code on the board. Both share two weaknesses:

1. **Remote cheating** – a photo of the QR / the code can be sent on WhatsApp to a friend at home.
2. **Check-in only** – a student can register in the first minute and leave five minutes later.

## 2. Our idea in one sentence
**The classroom itself proves presence:** the lecturer's laptop *broadcasts a short-lived token as sound*,
students' phones *hear it* and register automatically — and the same mechanism repeats during the lecture
as random **presence pulses**, so attendance measures *being there*, not just *arriving*.

## 3. Idea 1 — Acoustic check-in ("data over sound")
- The lecturer presses **Start class**; the laptop emits a short sound (≈1 s) that encodes a one-time token.
- Students open the web app on their phones, tap **Join class** (required by iOS to enable the microphone),
  and the phone decodes the token and sends it to the server together with the student's ID.
- Sound does not travel over WhatsApp in real time and fades with distance, so only people **physically in the room** can catch a valid token.
- **Library (compose, don't write):** [`ggwave`](https://github.com/ggerganov/ggwave) — MIT license,
  JavaScript/WebAssembly build that runs in the mobile browser; supports both *audible* and *ultrasound* protocols.

## 4. Idea 2 — Continuous presence ("pulses")
- During the lecture the server triggers **N random pulses** (e.g. 3 per lecture) at unpredictable times.
- Each pulse is again an acoustic token, sent by **ultrasound so it does not interrupt the lecture** (§6). If ultrasound fails in the real classroom, pulses move to natural pauses, typically together with a one-question KISS poll.
- A phone that hears the pulse answers automatically → the student gets a presence mark for that time slot.
- **Result:** the lecturer's spreadsheet shows not only *present / absent*, but **presence ratio**
  (e.g. 3/4 pulses) and participation — attendance becomes a by-product of engagement.
- This links **Feature 1 (attendance)** with **Feature 3 (polls)**.

## 5. Anti-cheating rules (design decisions)
| Threat | Mitigation |
|---|---|
| Recording the sound and replaying it to a friend later | Token is **one-time** and **short-lived** (TTL ≈ 20 s, to be tuned in tests) |
| Opening the site from home | Server accepts only tokens it just broadcast; no sound → no token |
| One phone registering several students | One device ↔ one student per lecture (device fingerprint / session cookie) |
| Check-in and leave | Random pulses during the lecture (Idea 2) |

## 6. Fallback (graceful degradation)
Sound may fail (weak laptop speakers, noisy room, a phone mic that filters high frequencies).
Fallback order:
**Design goal: the broadcast must not disturb the lecture**, so the intended default is ultrasound, subject to a real-device retest (§8).

1. Ultrasound protocol (near-inaudible) — **intended default** →
2. Audible protocol (short chirp, ≈1.6 s) — only outside teaching time, e.g. at check-in or a natural pause →
3. **Rotating QR code** on the projector (changes every ~15 s).

The fallback is a **requirement**, not an afterthought — the live demo must never depend on a single mechanism.

## 7. Building blocks
| Need | Tool |
|---|---|
| Server, REST API | Python + Flask |
| Real-time push of pulses / live dashboard | Flask-SocketIO |
| Storage | SQLite |
| Encode/decode token as sound | ggwave (JS/WASM) |
| Fallback QR | `qrcode` (Python) |
| Lecturer spreadsheet (online + offline) | Live dashboard + Excel/CSV export (`openpyxl`) |
| HTTPS for microphone access in class | ngrok / Cloudflare Tunnel |
| LLM features (video summary, homework review) | Claude API |

## 8. Must be tested in real life (feeds the Tools Report)
- [ ] ggwave decoding on **iPhone (Safari)** and **Android (Chrome)**.
- [ ] Ultrasound vs. audible: which works with the lecturer's laptop speakers?
- [ ] Maximum working distance (front row → last row) and behaviour in a noisy room.
- [ ] Microphone permission flow over HTTPS tunnel.
- [ ] ~40 phones registering at the same moment (load).

Suggested results table: *phone model × distance × protocol → success / fail*.
Spike page for these tests: `spike/sound-test/index.html` (has a built-in test log + CSV export).

### Spike findings so far (2026-11-08, digital loopback in browser, no speakers)
- ggwave 0.4.0 loads from CDN and encodes/decodes in the browser. ✅
- **`*_NORMAL` and `AUDIBLE_FASTEST` decoded correctly at every start offset tested.**
- **`*_FAST` sometimes returned corrupted bytes *without any error*** (depends on where the sound starts
  inside a 1024-sample frame — random in real life).
  → Design impact: never trust a decoded token blindly — validate its format (and ideally a check character)
  and let the **server** reject unknown tokens. Prefer `NORMAL` protocols (≈1.6 s per token).
- Creating two ggwave instances in the same page crashed the WASM module → use **one instance** per page.

### First real-device test (2026-11-08)
- Laptop speaker → real phone over HTTPS (Cloudflare quick tunnel), `AUDIBLE_NORMAL`, ~1 m: **received correctly**. ✅
- Second informal test: received **only with a clear line of sight / no wall between laptop and phone**; a wall blocked it.
  Medium speaker volume (user-reported); protocol presumably the page default, `AUDIBLE_NORMAL` (not confirmed).
  Distance and phone model were not recorded, so this is an observation, not a measurement.
  → Design impact: a blocking wall supports the "only people in the room" claim (a student in the corridor should not hear the token),
  but obstacles *inside* the room (pillars, a full class absorbing sound) may also cost reception — must be tested in the real classroom.

### Ultrasound test (2026-11-08)
- A first attempt was reported as "not received", but the laptop was on mute, so that attempt is void.
- **Retest with sound on: ultrasound was received on a real phone.** ✅ Short range, in a small room; exact ultrasound variant, Volume setting, distance and phone model were not recorded.
- The sound may still be faintly **audible from the laptop**, so "inaudible" is not yet established. To measure: find the lowest Volume that still decodes, and ask people in the room whether they hear it.
  → Ultrasound is the default (§6). Its range and how noticeable it is in a real classroom are still untested.
- Still to test: longer distances, other phone models, a real wall test with a recorded protocol (see checklist above).

## 9. How the other features fit (scope reminder)
1. **Attendance** – this concept (main feature).
2. **Comments & suggestions** – live feed, stored for offline reading.
3. **KISS polls** – also used as presence pulses.
4. **ML video summary** – upload recording/transcript → transcription → LLM summary (no Zoom integration).
5. **LLM homework review** – upload submissions → per-student review + cross-student comparison.

## 10. Open decisions
- Exact token TTL and length.
- Number and timing of pulses per lecture.
- Threshold for "present" (e.g. ≥ 2 of 3 pulses?).
- Optional: head-count from a class photo as an extra sanity check.
