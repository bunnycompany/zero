# Her — lineage: what the earlier HerApp thinking became

The Her branch (2026-09) did not have the earlier design conversation in
front of it. Its seven documents were supplied afterwards (`HerApp_MVP.md`,
`HerApp_on_Zero.md`, `HerApp_Chat.md`, `HerApp_MultiModel.md`,
`HerApp_Antigravity_Bridge.md`, `HerApp_Token_Economics.md`, `chatService.js`).
This page maps every idea in them to what exists now, so that nothing that
was decided twice gets decided a third time. Three verdicts are used:

- **kept** — exists today, possibly renamed
- **transformed** — the intent survives; the mechanism was replaced, and the reason is a written rule elsewhere in `docs/`
- **not built** — deliberately, with the reason; or simply not yet

Two eras are visible in those documents. The first ("HerApp MVP") is a
Swift/Vapor daemon with a Gemini API brain, a SQLite task queue, a cron
scheduler, JWT login with an admin password, a web UI served by the daemon,
an Android app, launchd, and Tailscale. The second ("HerApp on Zero" and
after) is the Node-era Zero: `agentStore.js`, `agentExecutor.js` spawning
`gemini --yolo`, WebSocket broadcast, a Cloudflare tunnel with a QR code, and
proposals layered on it. Today's Zero (July 2026 onward) is a third thing:
local Gemma 4, a file namespace, a tiered executor, shadow mode. Her sits on
that. `docs/failure-ledger.md` records why the second era was abandoned.

## The map

| earlier idea | verdict | where it is now, and why |
|---|---|---|
| An always-on agent on the Mac that you control from your phone | **kept** | `packaging/launchd/*.plist.template` (KeepAlive), the file inbox `command/inbox`, and `her/bridge.py`. Her is the phone-facing layer of exactly this. |
| Gemini API (2.0 Flash / `gemini-flash-latest`) as the brain | **transformed** | Local `mlx-community/gemma-4-e2b-it-4bit` is a hard rule (`CLAUDE.md`); a gateway brain (`brain/remote.py`) is optional. Reason: the privacy promise in `docs/product-model.md` — nothing leaves the Mac by default. |
| JWT login with an admin password (`/auth/login`) | **transformed** | Pairing by a six-letter code shown on the Mac, a device token hashed at rest, no password anywhere (`her/devices.py`). Reason: US-056 "a fingerprint, never a password"; `docs/reaching-zero.md`. |
| Task queue with priority and `dependsOn` chaining; a planner that turns a goal into 1–5 agents | **not built, deliberately** | Zero runs one command, one decision, one tool, one answer (`main.py`), FIFO, single-flight. Chaining and autonomous multi-step planning are the capability that the trust ladder gates; they come after the approve rung has a Yes button (US-034), not before. Reason: `docs/failure-ledger.md` #3 and #9. |
| Cron-like scheduler (`0 9 * * *`) | **kept** | `zero/scheduler.py`: `at` / `every`, firing into the inbox as `source: scheduler`. Cron syntax is not supported; natural-language times are still `needs-wiring` (US-021). |
| Web UI served by the daemon (login, ask box, task list) | **transformed** | The bridge serves `her/glasses/index.html` (a lens page). A general phone page served the same way is the next step, because it makes Her work on any phone with no app to install. |
| Android app (Retrofit, task list, run goal) | **transformed** | `android/` Her mode: pair, presence, an answer-her box and an ask box, `HerVoiceActivity`, a Glyph toy on the Nothing Phone (3). Not compiled on the Linux runner; see `docs/her-production-readiness.md`. |
| Android home-screen widget with `running / waiting / completedToday / scheduledJobs` | **transformed** | The Glyph Matrix toy is the widget (`HerGlyphToyService`). Per-day counts are not in the bridge snapshot yet; US-044 ("what did you actually do today?") is the story that wants them. |
| Chat from the phone into a persistent `gemini --chat` process, resumable by session id, with scrollback (`chatService.js`) | **transformed** | There is no process to resume. The journal (`namespace/log/journal.ndjson`) is the scrollback, the inbox holds what you type while the Mac sleeps ("offline is a promise", north star), and the bridge exposes the last answer. A history endpoint over the journal is the missing piece to make the phone "pick up where you left off". |
| WebSocket broadcast of every agent log line | **not built** | Surfaces poll files at 1 Hz (`gui/`, `her/cli.py`, the phone). Reason: `namespace/README.md` — a surface is a file reader, not an integration (`docs/failure-ledger.md` #4). |
| Cloudflare tunnel + QR code for reach from anywhere | **not built yet** | Relay is last in the order in `docs/reaching-zero.md`; the identity Worker in `identity/` exists and is not deployed. The bridge is home-wifi only. |
| Tailscale as the recommended remote path | **kept as the recommendation** | `docs/reaching-zero.md` says mesh first. **Action:** the bridge's private-address gate (`her/bridge.py::_is_private`) must accept the CGNAT range Tailscale uses (100.64.0.0/10), which Python's `is_private` does not; otherwise the recommended path is refused by the code. |
| Adaptive multi-model router (DeepSeek on a Mac Studio, MiniMax on a DGX Spark), learning from latency/quality feedback | **transformed** | Routing lives behind the gateway URL, not in Zero: `brain/remote.py` sends to `auto`, and `docs/fleet-brain.md` puts replication and health behind LiteLLM. Learned per-task routing is explicitly out of Zero ("no live ability probing in Zero", fleet-brain §5). |
| Token budgets with escalation approval ("use Claude for $0.50?") | **not built, deliberately** | `docs/product-model.md`: flat monthly, never per-token, no surprise bills. The descendant is the per-account concurrency cap in `docs/launch-blockers.md` §3. |
| Antigravity bridge: direct existing coding sessions from the phone by editing `task.md` / `plan.md` | **not built** | The pattern is alive in a different form: this branch was verified by firing a Routine into a Claude session on the founder's Mac. A "Projects" room (north star information architecture) is where this belongs later. |
| `[CHECKPOINT]` markers broadcast as progress | **kept** | `checkpoint/current` (executor) and the journal. |
| Modules "by addition, never modification" (`ModuleProtocol`) | **transformed** | The executor registry in `danger_core/executor.py` with tiers; a new tool is a registry entry plus a gate in `danger_core/gates.py`. |
| macOS notification via `osascript` | **kept, gated** | `her/presence.py::_notify`, only at the `live` presence level with a precision record. |
| "HerApp" as the product name | **transformed** | The daemon is Zero. Her is the companion layer: intake, presence, devices. `docs/her.md`. |
| MIT licence | **changed** | `UNLICENSED` in both npm packages; a founder decision, not yet made. |

## What the earlier thinking got right, and Her keeps

- The Mac is the anchor and the phone is the remote. The old design put a
  server on the Mac and a client on the phone; Her does too, with the
  namespace as the contract instead of a REST surface.
- "Never lose the session." The old `chatService.js` kept the process alive
  across phone disconnects and replayed scrollback. Her keeps the same
  promise with files: what you type waits in the inbox, and the journal is
  the record.
- Scheduling as the first proactive thing. Both eras built it first.
- Tailscale over port-forwarding. Both eras chose it.

## What to carry forward next, in order

1. Accept Tailscale's 100.64.0.0/10 in the bridge gate, with a test.
2. A `/v1/history` endpoint over the journal (your asks and Zero's answers,
   newest last) and per-day counts in the bridge snapshot, for the phone and
   for US-044.
3. A phone page served by the bridge (`/her/`), so Her works from any browser
   on the home wifi before the Android build is verified.
4. Natural-language times for the scheduler (US-021).
5. Only then the things the old documents wanted most and the trust ladder
   defers: an approve-rung Yes button, and after it, chains.
