# What the first Zero got wrong

Written 2026-07-30 from direct observation of the previous prototype (its two
screenshots, its data layout, and its own logs) before that store was detached.
This is not a post-mortem for its own sake: **every failure below is paired with
the invariant in this codebase that now prevents it, and where possible the test
that proves it.** A failure without an invariant is just a story. A failure with
a test is a closed loop.

Read this as a distance marker, not a condemnation. The first Zero is how far the
project got toward a genuinely noble goal: people should be able to trust their
computers more, and should not have to bend in half just to manage some agents. It
had a voice, presence, and an information architecture drawn from a person's life.
It lost that ground to nine specific, nameable engineering failures — and naming
them precisely is what lets the next attempt keep the distance already covered.

---

## 1. It could not talk back

**What happened.** The interface showed tool calls. A user asked for something and
got `read_file {path: ...}` where an answer should have been. The verdict in its
own logs was blunt: *"I'm not reading allat tool call crap."*

**Why it was fatal.** Acting without speaking is indistinguishable from being
broken, even when the action succeeded. Every other quality — speed, locality,
intelligence — is invisible if the user cannot tell what happened.

**Invariant now.** Every turn produces exactly one plain-English sentence, on a
dedicated `answer` channel that is separate from the machine-readable `action`
channel. The model composes it; if the model produces nothing speakable, a
deterministic fallback speaks instead.
`brain/answer.py` · proved by `tests/test_answer.py` (never empty, never JSON,
never a payload, never a stack trace)

---

## 2. Its failures were silent

**What happened.** `Error: Lost connection to gemini-cli session` appears inline in
the transcript, and the conversation simply stops. Elsewhere the user typed
*"sorry my bad"* — **the human apologising to the broken agent**, which is the
clearest possible signal that the software had trained them to absorb its faults.

**Why it was fatal.** A failure the user cannot see is worse than a crash. They
conclude they asked wrong.

**Invariant now.** Failures are answers too, phrased plainly with what to try next
("I tried, but that file doesn't exist. Want me to try a different way?").
Unparseable model output is journaled *and* spoken. A silent brain is treated as a
harness error, never a passing score — that check exists because a dead gateway
once "scored" 7/9 on our own eval.
`main.py::say` · `zero/agenteval/run.py` brain-silent guard

---

## 3. It was built to recover from crashing instead of not crashing

**What happened.** The data directory contained `reincarnation-logs.jsonl`,
`reincarnation-state.json`, a `crash-logs/` directory, and hand-made safety copies
(`agents.json.backup`, `agents.json.bak`).

**Why it was fatal.** Machinery for coming back from the dead is an admission that
dying is routine. The `.bak` files say the author did not trust the state store.

**Invariant now.** Mutations never auto-retry (retries are READ-tier only, by
rule). All state writes are atomic — temp file, fsync, rename — so a crash cannot
produce a half-written file. One writer per channel, mechanically enforced, so
corruption has no path in.
`danger_core/executor.py` · `zero/ns.py::OWNERS` · `tests/test_ns.py`

**Still open:** a crash between claiming a command and finishing it loses that
command. Claim-then-recover is not built yet.

---

## 4. Surface sprawl: many front doors, none finished

**What happened.** Web app, TUI, Android app, glasses, a WebXR experiment, wearables
bridges, plus several agent subsystems — all in one tree, alongside four different
coding-agent configs.

**Why it was fatal.** Every surface multiplies the cost of every change, and none of
them got finished well enough to be the one a person uses daily.

**Invariant now.** Surfaces are thin readers of the same plain files. The namespace
is the contract, so a new surface is a file reader and not an integration. The rule
is one surface finished at a time.
`namespace/README.md`

---

## 5. It performed a personality instead of having one

**What happened.** Asked *"you're fast what model are you"*, it answered: *"you can
think of me as Zero. I'm a sophisticated AI companion…"* — marketing copy in place
of the plain fact of which model was running.

**Why it was fatal.** Evasion about itself teaches the user that its statements are
promotional rather than true. Warmth is earned by accuracy, and spent by flattery.

**Invariant now.** The model name is visible in the interface, always. Zero
describes what it did, not what it is. When it cannot do something it says so
instead of reframing.

---

## 6. The user had to speak the system's language

**What happened.** Real user messages included *"what agents do we have blocked in
herdr"* — internal subsystem names in what was supposed to be ordinary conversation.

**Why it was fatal.** For an audience who does not want to use the computer, every
piece of internal vocabulary is a wall.

**Invariant now.** No internal noun reaches the user. States are "Ready", "Thinking",
"Working on it" — never `idle`/`executing`. Tool names are phrased as actions
("looked in that folder"). The copy rule: a person manages *notifications*, not
*webhook config*.
`brain/answer.py::_PHRASING` · `gui/…/ZeroUI.swift::headline`

---

## 7. The chat window became a debugger

**What happened.** The transcript contains *"run echo LIVEUPDATE_OK in the shell"*
and *"run echo CHIPTEST123"* — the author using the product's chat interface to
check whether the product was alive.

**Why it was fatal.** When the only way to test liveness is to ask it to echo a
string, there is no liveness signal. The user is doing the monitoring.

**Invariant now.** Liveness is a first-class, glanceable fact: the UI reads the
status file's freshness and shows grey "Zero isn't running" when stale, and
`zero status` answers the question in one line.

---

## 8. A dead surface with nothing to say

**What happened.** The empty state read *"No active projects"*, centred in a black
screen, with no next step.

**Why it was fatal.** First contact is where a non-technical user decides whether
this is for them. An empty room with a label is a dead end.

**Invariant now.** The first run teaches instead of reporting emptiness: `zero` with
no history prints what to say, how to read replies, and what shadow mode means.
`scripts/zero::_greet`

---

## 9. It sprawled outward before the middle worked

**What happened.** Caches and evidence directories for Tesla, Eufy cameras, a
kitchen, generated images and browser screenshots — home-automation reach — while
the core loop was still losing sessions.

**Why it was fatal.** Breadth bought demos, not trust. Each integration added a way
to fail in front of someone.

**Invariant now.** Capability is gated behind tiers and modes, and the honest gaps
are published rather than hidden: no reminders, no calendar, no messages, no screen
access, no proactivity. It says so when asked.

**Now carried back.** The old Zero *had* `scheduled_tasks.json`, and it was the one
capability it had that the new one lacked — the difference between a tool you operate
and an assistant that shows up. As of 2026-07-30 the new Zero has it too
(`zero/scheduler.py`): a rule you wrote fires into the same command inbox as a human
ask, tagged `source: scheduler` so it never pollutes the proactivity ground truth.
Verified end to end — a scheduled reminder travelled the whole loop with no human
touching the queue.

---

## What it got right, and we should not lose

- **A voice.** *"I'm here to help you navigate your digital world, whether that means
  tackling complex projects, organizing your files, or just exploring what's
  possible."* Warm, first-person, unhurried. The register to grow into — minus the
  self-description.
- **An information architecture of a person's life**, not a system's:
  **Projects · Inbox · Camera · Tasks**. Nouns anyone recognises. Today's Zero has
  one chat box; those are the rooms it eventually needs.
- **It scheduled things.** See above.

---

## How this closes the loop

Failures 1, 2, 6, 7 and 8 are now invariants with tests. Failures 3 and 4 are
invariants with partial coverage. Failures 5 and 9 are editorial commitments held by
this document and the north star, which is the weakest form of enforcement — if
either starts drifting, the fix is a test, not a reminder.

The rule going forward: **a promise on the landing page must map to a user story,
and a user story must map to a check that can fail.** Anything that cannot fail is
decoration. `python -m zero.agenteval.coverage` prints which promises currently have
a check behind them; it is at 9/9 and should never be allowed to fall.

And the test that sits above all of them: **does this let the human check less?**
Zero exists to reduce time spent at the computer, so every feature that adds a knob,
a dashboard, or one more thing to verify is moving away from the goal even when it
demos well. Managing the agent is the tax the agent was supposed to abolish.
