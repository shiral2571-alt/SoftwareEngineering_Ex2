# Sound Attendance Spike — how to run

Proof-of-concept for [docs/CONCEPT.md](../../docs/CONCEPT.md): can a laptop speaker send a token to phones over sound (ggwave)?

## Start (two terminals, from the project root)

```bash
py -m http.server 8765 --bind 127.0.0.1 --directory spike/sound-test
```

```bash
cloudflared tunnel --url http://localhost:8765
```

- **Laptop** → open `http://localhost:8765` → **Broadcast**.
- **Phone** → open the `https://….trycloudflare.com` address printed by cloudflared → **Listen** → *Start listening*.
  (The address is new every time the tunnel starts. HTTPS is required for microphone access.)

Stop both with `Ctrl+C` when done — the tunnel makes the page public while it runs.

## Status
- ✅ 2026-11-08 — `AUDIBLE_NORMAL`, ~1 m, real phone: received.
- ✅ 2026-11-08 — Ultrasound, real phone, short range: received once the laptop was unmuted (an earlier attempt on mute is void). May still be faintly audible from the laptop. Longer range (row 3) still to test.
- ⏳ Pending (needs a bigger room):

| # | Protocol | Distance | Question |
|---|---|---|---|
| 1 | Audible – normal | 3 m, 5 m | Does it reach the back row? |
| 2 | Ultrasound – normal | 1 m | Can the laptop speaker produce it at all? |
| 3 | Ultrasound – normal | 3 m | Only if #2 passed |
| 4 | Audible – normal | 1 m + background noise | Classroom noise |
| 5 | Any working protocol | — | A second phone model (iPhone ↔ Android) |

Log each attempt in the page's **Test log** and press **Download CSV** at the end — that CSV goes into the Tools Report.
