# Her — the part of Zero that gets to know you

A design note and a status ledger, written as the code landed. Read
`north-star.html`, `proactivity.md` and `reaching-zero.md` first; Her is
those three notes, built.

## What Her is

Her is the companion layer over Zero: she gets to know you the way a person in
a box would — one question at a time, over days — she is already there when you
turn your attention to her, and she reaches the devices you paired. She is not
a second agent. She has no brain of her own and no executor of her own; every
ask from a Her surface goes through `command/inbox` like a keystroke at the
Mac, and every fact she keeps is a line in `namespace/memory` you can read or
strike out yourself.

The one property that makes her "low fallibility", stated as a rule the code
keeps:

> **Her never claims to know something about you that you did not say.**

Mechanically: the questions are scripted (she cannot invent one that presumes
something about you); your answers are stored verbatim with an `origin` of
`intake:<question>`; only those facts are rendered into the pinned profile
block every decision and every answer sees first; the model may *add* facts it
inferred, and `her profile` marks those `inferred`, never `you said`. When she
speaks about a date or a person, it is a quotation with a timestamp
("You told me: … (said 1 Sep 2026)"), not a paraphrase.

## Three ladders, all human-only

| ladder | file | rungs | what Her may never do |
|---|---|---|---|
| action (Zero's) | `control/mode` | shadow → approve → live | write it |
| speech (Her's) | `control/presence` | quiet → digest → ambient → live | write it, or deliver above it |
| reach (devices) | `her pair`, `her glasses` | nothing → phone → glasses | pair without a code you opened |

`quiet` is the default and where a fresh install stays: with no history there is
nothing to say, so a new Her is silent by construction. She still forms
opinions — into `her/unsent.ndjson`, the shadow log of speech — and `her review`
lets you say, line by line, *would I have wanted this?* `live` (a real
notification, level 2) is only honoured with a record: 20 reviewed lines at 80%
wanted. Without it, a `live` setting delivers as `ambient` and the journal says
so. A device is a `source` the executor does not trust (`policy.effective_mode`),
so a paired phone can ask and can never act — even with the Mac in `live`.

## What is built (v0, this branch)

| piece | where | proved by |
|---|---|---|
| intake: paced deck, verbatim facts with provenance, skip/retire, pace of 3/day | `her/intake.py` | `tests/test_her_intake.py` |
| profile block rendered only from what you said; strike-out stamps, never deletes | `her/profile.py`, `zero/memory.py`, `zero/consolidator.py` | same |
| main-loop hook: a `reply_to` answer never reaches `decide()` or a tool | `main.py::handle_commands` | `test_main_loop_routes_reply_to_intake_not_decide` |
| presence: the line + a ≤40-char glance, on events only, no model call | `her/presence.py` | `tests/test_her_presence.py` |
| unsent log, ladder, precision gate, dedup; triggers are rules (a date you told her, a repeated ask, a reminder about to fire, her own watcher dying) | `her/presence.py` | same |
| pairing by six-letter code, token hashed at rest, five wrong tries burn the code, `forget` = dead key | `her/devices.py` | `tests/test_her_bridge.py` |
| LAN bridge: private addresses only, binds a port only while there is someone to listen for | `her/bridge.py` | same, over a real loopback socket |
| `her` CLI | `her/cli.py`, `scripts/her` | `tests/test_her_cli.py` |
| menubar: her line, her question in its own box, `sparkle` only on human-set attention | `gui/Sources/ZeroUI/ZeroUI.swift` | **not compiled here** (no Swift on this runner) |
| phone: pair, presence, answer-her box, ask box, voice path; Glyph toy on the Nothing Phone (3) | `android/.../her/`, `android/app/src/nothing/` | `HerGlyphArtTest.kt`; **not compiled here** (no Android SDK on this runner) |
| glasses: one-glance page for the Ray-Ban Display, served by the bridge | `her/glasses/index.html` | served + read in `test_token_in_query_works_for_the_glasses_page` |
| `npx @0-computer/her` | `npm-her/` | `node bin/her.js help` runs; depends on `@0-computer/zero`, unpublished |
| model-layer scenarios: recalls the name you gave; abstains on a person you never mentioned | `zero/agenteval/scenarios.py` (`her_*`) | **not run here** (needs the model on a Mac) |

Wiring layer: 146 tests, green on Linux with no MLX (the local brain now fails
at load time, not import time, so the suite runs anywhere).

## The devices, and what is actually true about them

Everything below was checked against the vendors' own pages on 2026-09-01.
Where a claim is not verified, it says so.

**MacBook Neo** (A18 Pro, 8 GB unified, 2026) — the anchor. The default model
(`mlx-community/gemma-4-e2b-it-4bit`, ~3.6 GB) fits; the bigger gemma-4
variants do not and go through the gateway brain. Her adds no model load: her
presence is a file rewrite and her intake is deterministic, so an 8 GB machine
pays nothing extra for her. The bridge is one Python process that sleeps until
a device is paired.

**Nothing Phone (3)** — the Glyph Matrix is a 25×25 LED matrix on the back with
a public developer kit (Nothing-Developer-Programme/GlyphMatrix-Developer-Kit):
a toy is an exported `Service` answering `com.nothing.glyph.TOY`, frames are
`int[625]` via `GlyphMatrixManager.setMatrixFrame`, and the system sends
`EVENT_CHANGE` on a long press of the Glyph button and `EVENT_AOD` once a
minute on the always-on display. Her uses exactly those: her presence as light
(a breathing ring, a travelling dot while Zero thinks, a `?` when she has a
question, a filled centre only when a human-set level says something is
there), and long-press = talk to her. The `nothing` product flavor needs the
SDK's `.aar` dropped into `app/libs/`; the `plain` flavor builds without it.
The Essential Key has no public API; Her is instead offered as the assist app
(`ACTION_ASSIST`) so any long-press-home gesture reaches her.

**Ray-Ban Meta Display** — as of May 2026 Meta's Wearables Device Access
Toolkit has a developer preview for the in-lens display: native Kotlin/Swift
components (text, images, lists, buttons, video), and **web apps** — plain
HTML/CSS/JS hosted at a URL, added through the Meta AI app in Developer Mode,
running on the glasses without a companion app, with Neural Band input.
`her/glasses/index.html` is such a page: black ground, one glance line, the
full line, her open question. **Not verified:** that the glasses' web runtime
can reach a private LAN address (the docs do not say); if it cannot, the page
needs the relay from `reaching-zero.md`, which is not built. Publishing is not
yet available in the preview; a build is limited to 100 testers.

**Ray-Ban Meta, any generation** — reach a phone as a Bluetooth headset; the
toolkit's own FAQ says microphone/audio go "through iOS or Android Bluetooth
profiles". So the voice path needs no Meta SDK at all: `HerVoiceActivity`
listens with `SpeechRecognizer`, sends to the bridge, and speaks the answer
with `TextToSpeech`, and whatever headset is connected is where that lands.

## How it feels, day one to day ten

```
$ npx @0-computer/her setup        # Zero's own setup; nothing extra
$ her
  Her › Evening. Nothing needs you. One question when you have a moment.

  she asks › What should I call you?
$ her Dal
  Her › Got it — Dal it is. And what would you like to call me? Her is fine, or pick anything.
```

Three questions a day, ten in all. Skip any; say "never" and it is gone for
good. `her profile` shows every line with an id; `her forget <id>` crosses one
out (kept, stamped, never used). `her pair` for the phone, `her glasses` for
the Display. `her unsent` is what she would have said; `her review` is how
she earns the right to say it. Only `echo ambient > namespace/control/presence`,
by your hand, lets any of it reach you.

## Honest gaps

- Swift and Kotlin were written to the existing code's conventions and the
  vendors' documented APIs but **were not compiled on this runner**. First
  `cd gui && swift build` and `./gradlew :app:assemblePlainDebug` on a Mac
  may turn up typos; the logic is small.
- The model-layer scenarios (`her_*`) have not been run: they need the model.
- The Display page's LAN reach is unverified (above).
- `her/devices/current` has one *nominal* writer (`bridge`) but the `her` CLI
  also writes it for a local pair/forget; two rare read-modify-writes can race
  in a window of milliseconds. Fixing it properly means routing CLI pairing
  through the bridge; not done.
- Intake answers from a paired phone are accepted (they are memory, not a
  mutation); a stolen phone could tell Her things. It still cannot act.
- No relay, no identity: Her is home-wifi only, per the order in `reaching-zero.md`.

## What comes next, in order

1. Compile and run the two UIs on real hardware; fix what the compiler finds.
2. Run the `her_*` scenarios; if e2b fails to recall the name, it is a prompt
   bug in `brain/answer.py` (the core block is already injected), not capacity.
3. A glasses test on a real Display: does the web runtime reach `192.168.x.x`?
4. `digest` in daily use for a week, then `her review`, then decide whether
   `ambient` is worth it — the proactivity note's step 4, unchanged.
5. Publish `@0-computer/zero`, then `@0-computer/her`, in that order.
