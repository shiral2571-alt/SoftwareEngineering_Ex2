# Technical Tools Report

Assignment To-Do #3: *"Perform a technical-related tools report — make sure to test (in real life) with any suggested tool."*
For each tool: why we chose it, the alternatives, **what we tested in real life and the result**, and how the result changed the design. Raw test notes are in [CONCEPT.md §8](CONCEPT.md). Design decisions (D-n) are in the [SRS](SRS.md).

> **Honesty note.** Distances and phone models were not always recorded in the early tests. Results marked *not recorded* are observations, not measurements. The lecture-hall test is still planned (§6).

---

## 1. Data over sound: ggwave 0.4.0 (JS/WASM, MIT)
**Why:** it lets the classroom itself prove presence. A code played by the lecturer's laptop cannot be photographed and sent on WhatsApp, unlike a static QR. ggwave runs entirely in the phone's browser (WebAssembly), with no app to install.
**Alternatives considered:** a static QR code (shareable); a rotating QR (kept as an equal alternative); Bluetooth or Wi-Fi proximity (not available to web pages on iPhone); commercial ultrasonic SDKs such as LISNR (paid, and they need native apps).

### Tests
| # | Date | Setup | Protocol | Result |
|---|---|---|---|---|
| T1 | 11-08 | Digital loopback in the browser (no speakers), many start offsets | `*_NORMAL`, `AUDIBLE_FASTEST` | ✅ Always decoded correctly |
| T2 | 11-08 | Same | `*_FAST` | ⚠️ **Sometimes returned corrupted text with no error** |
| T3 | 11-08 | Two ggwave instances in one page | — | ❌ The WASM module crashed (`Aborted()`) |
| T4 | 11-08 | Laptop speaker → real phone, about 1 m, HTTPS tunnel | Audible normal | ✅ Received |
| T5 | 11-08 | Same, with a wall between them | Audible normal | ❌ Blocked by the wall; received only in line of sight |
| T6 | 11-08 | Laptop speaker → phone, short range, small room (an earlier attempt with the laptop muted is void) | Ultrasound normal | ✅ Received, but faintly audible from the laptop |
| T7 | 11-10 | Full app, real phone | Ultrasound, volume 50 | ⚠️ Received **only very close** to the laptop |
| T8 | 11-10 | Full app, real phone | Audible normal | ✅ Received further away |
| T9 | 11-17 | Full app, real phone, *get ready early* | Audible normal | ✅ Checked in on the **first** broadcast; mic closed afterwards |
| T10 | 11-17 | Same phone and setup | Ultrasound | ❌ Not received |

### Impact on the design
- **Use only `NORMAL` protocols, and never trust a decoded string** (T2). The phone checks the code's shape, and the server rejects any code it did not just issue.
- **One ggwave instance per page** (T3).
- **Audible sound is the default, and ultrasound is only an option** (T7, T10 → D-2). Audible sound does not disturb, because the lecture pauses for check-in anyway.
- **A wall blocks the sound** (T5). This supports "only people in the room", but obstacles inside a big hall are a risk, so the QR is an equal alternative (SoW R-1).
- **Students can get ready before the sound starts** (D-16). In the 11-16 phone test the *Check in* button appeared only after the sound had started, so the first broadcast was missed. T9 confirms the fix.
- *Not recorded:* exact distances and phone models. These will be measured in the hall test.

## 2. HTTPS for phones: Cloudflare quick tunnel (`cloudflared`)
**Why:** browsers allow the microphone only on HTTPS, and phones cannot reach `localhost`. A quick tunnel gives a public HTTPS address in one command, with no account. **Alternatives:** ngrok (needs an account), a self-signed certificate (phones reject it), cloud hosting (future work).

| Test | Result |
|---|---|
| Phone opens the app and grants the mic over the tunnel | ✅ Works |
| Tunnel lifetime | ⚠️ The address changes on every run, and quick tunnels sometimes expire ("Tunnel not found"). Restarting fixes it |
| A different network (11-16) | ❌ The laptop's network DNS could not resolve `*.trycloudflare.com`, although the tunnel worked from outside. Phones on mobile data worked |

**Impact:** the lecturer dashboard runs on `localhost`, and phones use mobile data. A backup network (phone hotspot) is in the demo plan (SoW R-2). The *Join QR* always encodes the current address, so a changing address is not a problem.

## 3. Web framework and storage: Flask + SQLite
**Why:** Flask is minimal, easy to read and easy to test with `test_client()`. SQLite needs no server: a single file. **Alternatives:** Django (too heavy for KISS), FastAPI (async adds complexity we did not need).
**Tested:** 49 automated tests ([Testing strategy](TESTING_STRATEGY.md)); real phones and laptop during all tests above.
**Live updates:** short polling every 2–3 s instead of WebSockets (D-13). Simpler, and it works through the tunnel. **Real-life finding:** polling rebuilt the materials list every 3 s, so items the student opened kept closing on the phone. Fixed by rebuilding only when the data changes.

## 4. QR codes: qrcode-generator 1.4.4 (JS)
**Why:** it draws the QR in the browser, with no server image generation. **Tested:** the QR renders, encodes the current tunnel address, and rotates every 15 s. A phone-camera scan through the tunnel is still to be confirmed in the demo rehearsal.

## 5. Spreadsheets: openpyxl
**Why:** reads the lecturer's xlsx class list and writes the offline Excel sheet. **Tested:** xlsx import with Hebrew headers, and export (overview, one sheet per lecture, polls, forum), in automated tests.

## 6. AI providers: Claude, Gemini, OpenAI (official SDKs)
**Why:** the assignment asks for "LLM-ready" tools. Lecturers use different providers, so the provider is a setting behind one `LLMClient` interface (Strategy pattern, D-11). Models offered: 2–3 per provider, from cheap/fast to strongest (D-15). The names were checked against the providers' documentation on 2026-11-16.

| Test | Provider and model | Result |
|---|---|---|
| Teaching feedback, real lecture transcript copied from Zoom, run 1 | Gemini 3.5 Flash-Lite | ✅ Followed the 5-section structure. ✅ Refused to guess: "student questions cannot be counted reliably because speakers are not labelled". ✅ Found a commitment and listed it as a task. ❌ **Answered in English** |
| Same, after the prompt was given Hebrew headings (D-18) | Gemini 3.5 Flash-Lite | ✅ **Answered in Hebrew** |
| Input check | — | ⚠️ The first copy from Zoom's panel captured only **1,671 of 4,557 words**, so run 1 judged a third of the lecture. Our "Words" statistic revealed this |
| Claude, OpenAI | — | ⚠️ The code path is implemented and unit-tested with fakes; **not run against the real API** (no key available) |
| No key, or no internet | Offline fallback | ✅ The measured statistics are still shown; nothing crashes |

**Impact:**
- **Hebrew section headings in the prompt** (D-18): small models copy the headings' language.
- **Every report names its model** (FR-7.6a), so results can be compared.
- **The prompt forbids guessing**, and the measured statistics act as an input check.
- **Prefer a .vtt file** over copying from Zoom's panel: timings enable pace statistics, and nothing is lost.
- **Privacy:** the transcript is sent to the chosen provider. This is acceptable for a course test, and must be stated to users.

## 7. Testing: pytest
**Why:** the standard Python test runner; fixtures and a fake clock keep the tests fast and deterministic. **Result:** 49 tests in about 4 s, with no network.

## 8. Still to test before the demo
| Test | Why | Pass criterion |
|---|---|---|
| **The lecture hall:** back row, 2–3 phones, audible | The biggest demo risk | Every phone checks in within 30 s of *Start check-in*; otherwise switch the demo to QR |
| QR scan from a phone through the tunnel | Not yet confirmed | The scan opens the app and checks in |
| 3–5 phones at once | A small load test | Everyone checks in; the counter is correct |
| *(Optional)* The sound relayed over a WhatsApp call | The relay risk E13 | Record whether it decodes. Either result goes into this report |
