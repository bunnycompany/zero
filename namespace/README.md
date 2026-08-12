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
