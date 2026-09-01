# The Zero namespace

Agent state as plain files. Any process — Python, Swift, or you with `cat` —
reads the same surface. Two rules make it work:

1. **Exactly one writer per state file.** Enforced by `zero/ns.py` (OWNERS).
2. **All writes are atomic** (temp + fsync + rename). Plain `echo x > file`
   from a shell is fine for debugging; it's atomic enough at this size.

The namespace must live on a **local APFS volume** — never iCloud Drive,
Dropbox, or a network mount (rename atomicity and ordering break there).

| path | format | writer | readers | semantics |
|---|---|---|---|---|
| `status/current` | text | main loop | Swift UI, humans | heartbeat: `idle` \| `thinking` \| `executing` \| `error` |
| `context/current` | JSON doc | observer | main loop | what the observer currently sees `{app, ...}` |
| `action/current` | JSON doc | brain | Swift UI, humans | last decision the brain emitted (display only — danger_core gets its input via function call, never by re-reading this file) |
| `checkpoint/current` | JSON doc | executor | humans, recovery | durability record `{last_tool, ...}` |
| `control/mode` | text | **human only** | executor | `shadow` \| `approve` \| `live`. Read on every call, never cached: `echo shadow > control/mode` is the panic button. The agent may never write here. |
| `command/inbox/*.json` | JSON doc | Swift UI / CLI | main loop | user commands, one file per submission (queue — never clobbered) |
| `command/done/*.json` | JSON doc | main loop (rename) | humans | consumed commands; free audit trail, pruned after 7 days |
| `log/journal.ndjson` | ndjson | any (append) | humans, tools | append-only journal. `current` files answer "what now"; only this answers "what happened". Rolls to `.1`-`.3` past 10MB (`zero/ns.py::_rotate_journal_if_needed`); older history is dropped, not archived. |

JSON doc envelope: `{"v": 1, "ts": <unix>, "writer": "<name>", "payload": {...}}`.

Filenames in a channel dir are `current` or `*.json` — nothing else. Writers
use a `.tmp-` prefix for in-flight files so globs never see them.

## Memory channels (memory-v0)

| path | format | writer | readers | semantics |
|---|---|---|---|---|
| `memory/observations/inbox/*.json` | JSON doc | brain | consolidator | candidate facts, one per file, claim-by-rename queue |
| `memory/observations/done/*.json` | JSON doc | consolidator (rename) | humans | consumed observations, audit trail |
| `memory/facts/current.ndjson` | ndjson | consolidator | brain | ADD-only facts; contradiction = `ts_invalidated` stamp, never deletion |
| `memory/core/current` | text | consolidator | brain | pinned profile block, injected verbatim, hard cap ~800 tokens |

Read path: `zero/memory.py::render()` — keyword × recency × importance over
ndjson, ≤1.5K tokens injected into `decide()`. No embeddings by design until
the scorer measurably misses.

| `answer/current` | JSON doc | main | UIs, humans, `zero` CLI | what Zero says back, in plain English — written every single turn, successes and failures alike |

## Her channels (her-v0)

Her is the companion layer: it gets to know you, is present when you look,
and reaches the devices you paired. It never gets a second brain or a second
executor — every ask from a Her surface goes through `command/inbox` like any
other. Its own state lives beside the agent's:

| path | format | writer | readers | semantics |
|---|---|---|---|---|
| `her/intake/current` | JSON doc | her | UIs, `her` CLI | getting-to-know-you state: which questions were asked, answered (verbatim), skipped, retired |
| `her/presence/current` | JSON doc | her | UIs, bridge, `her` CLI | level-0 presence: `{line, glance, state, question, attention}` — what is already there when you look. `glance` ≤ 40 chars for a lens or a Glyph |
| `her/unsent.ndjson` | ndjson | her (append) | humans (`her review`) | what Her *would* have said and when. Shadow mode for speech: nothing here is delivered while `control/presence` is `quiet`. Review verdicts append to the same file |
| `her/pairing/current` | JSON doc | her | bridge | the one live pairing code (10 min). Absent = no device may pair and the bridge has nothing to listen for |
| `her/devices/current` | JSON doc | bridge (the `her` CLI for a local pair/forget) | UIs, `her` CLI | paired devices: `{id: {name, kind, token_sha256, paired, last_seen}}`. The token itself is shown once and never stored |
| `control/presence` | text | **human only** | her | `quiet` \| `digest` \| `ambient` \| `live`. Missing or unknown reads as `quiet`. Read on every tick, never cached. Her may never write here — same rule as `control/mode` |

Commands submitted from a Her surface carry extra payload keys: `reply_to`
(the intake question this text answers) and `device` (which paired device
spoke). Device sources (`phone`, `glasses`) are untrusted to `policy.effective_mode`
and are capped at `approve` regardless of the real mode.
