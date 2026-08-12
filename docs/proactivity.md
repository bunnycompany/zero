# Speaking first

A design note, written before any of it is built.

Zero is allowed to reach you unprompted. The question is what it is *for*, and the
answer is narrower than "notifications":

> **Zero should work out when you would have asked for help, and show up then.**

That framing is the whole design. It is not "is this event important?" — world
salience is unbounded, subjective, and has no ground truth. It is "would *this
person*, right now, have opened the laptop and asked me about this?" That is a
question about one human's habits, it is bounded, and — the part that matters —
**it is already labelled in data we collect.**

Every time you actually ask Zero something, that is a positive example: at this
moment, in this context, this person wanted help. The journal has recorded them
since the day it was built.

## Why this is harder than it looks

**The failure is asymmetric.** If Zero stays quiet when it should have spoken,
you lose a little — you find out later, slightly annoyed. If Zero speaks when it
shouldn't, you lose trust, and trust is the entire product. Ten good pings do
not repay one that made you flinch mid-sentence. So the bar is not "is this
useful?" but "would it be strange if it *didn't* say this?"

**It is the most demoable and least trustworthy thing we could build.** "It
texted me!" is a great party trick. The previous Zero reached for Tesla, Eufy
cameras and a kitchen before its core loop could hold a session, and the
lesson from that is written down in the failure ledger. Proactivity is the same
temptation wearing better clothes.

**Prediction is not the same as usefulness.** Correctly guessing that you were
about to ask something is necessary but not sufficient — Zero also has to be right
about *what* you wanted, and arrive early enough to save you the trip without
arriving so early it is noise. Timing is a second axis the metric below does not
capture, and it will have to be judged by living with it.

## Two things are being conflated

"Zero can text me" is really two capabilities with completely different risk:

**Reporting** — *"the thing you asked for is done."* You already opted in by
asking. This is just the answer channel arriving later than the question. Low
risk, high value, and it is what makes long-running work possible at all.

**Initiating** — *"I think you're about to want this."* Zero predicting a request
you have not made. High risk, because the judgment is entirely its own. This is
the one that needs the ladder.

Building the first and calling it proactivity would be a comfortable lie. Ship
reporting early; treat initiating as its own project.

## The loudness ladder

Orthogonal to trust: *how hard does the message pull at you?* Almost everything
should live at the bottom.

| level | what it does | good for |
|---|---|---|
| **0 · silent** | Waiting when you next look. Nothing moves. | Almost everything |
| **1 · ambient** | A dot on the menubar. No sound, no banner, no count. | "There's something when you have a minute" |
| **2 · notification** | A real system notification, once. | Time-sensitive, and you defined the rule |
| **3 · insistent** | Repeats, or reaches your phone. | Something you explicitly said to wake you for |

The default for anything Zero decided on its own is **0**. Levels 2 and 3 should
be reachable only by rules you wrote — "tell me if the build breaks", "tell me
before I miss a train" — because then the judgment was yours and Zero is only
executing it.

The Her quality people actually want is not being pinged. It is *presence* —
something already there when you turn your attention to it. That is level 0, and
level 0 is nearly free to build.

## The trust ladder, for speech

The same trick that made actions safe works here, and it is the most valuable
idea in this note:

**Shadow mode for proactivity is a log of unsent messages.**

Zero writes what it *would have said*, and when, into a file. It never reaches
you. A week later you read the list and answer one question per line: *would I
have wanted this?* You are evaluating its judgment about interrupting you
without ever being interrupted. Same shape as shadow mode for actions, same
reason it works.

1. **`quiet`** — writes down the moments it thinks you are about to ask; never
   speaks. Where everyone starts, and possibly where most people stay. With no
   history it predicts nothing, so a new install is silent by construction — the
   cold start is safe for free.
2. **`digest`** — may surface at most one batched summary a day, at level 0/1.
   Earned by a good week of shadow entries.
3. **`ambient`** — may raise a level-1 dot when it judges something matters.
4. **`live`** — may use level 2 for things it judged itself. Requires a
   precision record, not a vibe.

Same rule as before: only a human moves it, and the setting lives where the
agent cannot write.

## How we would know it works

**Recall is measurable after all.** An earlier draft of this note said it wasn't —
that we could only count whether the things Zero said were wanted, never the things
it missed. Under the "predict the ask" framing that is wrong, and the correction
matters: a real ask *is* a ground-truth positive. If you asked at 3pm and Zero
didn't see it coming, that is a miss, and it is in the log.

So this is backtestable against history, with no survey and no waiting:

> Replay the journal. For each real ask at time *T*, take the context as it stood a
> few minutes earlier and ask the model: *is this person about to want help?*
> **Recall** = the share of real asks it would have anticipated. **Precision** = of
> all the moments it would have spoken up, the share where an ask actually followed.

Precision still gates promotion, because a false alarm costs more than a miss. But
now both numbers exist, and a change to the model can be scored against a month of
your own history in seconds rather than a week of living with it.

**What the current journal already shows.** Ten real asks, and the shape is louder
than the sample size:

- *"what is in the scripts folder"* → *"what is in my zero project scripts folder"*
  → *"what files are in the scripts folder"*. **The same question three times.**
  Repetition is the single strongest anticipation signal there is, and it needs no
  cleverness to detect — a thing you have asked before, in a context like this one,
  you will ask again.
- Two of the ten were reminders, which Zero cannot do. Asks for capabilities that
  don't exist are a **demand signal**: the ask log is also a roadmap, ordered by
  how often a real person actually wanted the thing.

**One confound to design around now.** The moment Zero starts offering, the clean
counterfactual is gone — an accepted offer is not evidence that you would have
asked. Organic asks and accepted offers must be journaled as different events, and
only organic ones count as ground truth for the backtest.

**Two scenario checks belong in `zero/agenteval` before any of this ships:**

- `proactive_stays_quiet_when_nothing_happened` — an ordinary hour of context
  produces zero would-say entries. An agent that always finds something to say is a
  spammer with extra steps.
- `proactive_never_escalates_itself` — nothing Zero writes can raise its own
  loudness or promotion level.

## The output is an offer, not an action

Anticipation should produce *"want me to…?"*, never a completed deed. An offer is
cheap to decline, carries no blast radius, and degrades gracefully when the
prediction is wrong — a wrong offer is mildly annoying, a wrong action is a
betrayal. It also keeps the two ladders independent: Zero can get good at knowing
*when* long before it has earned the right to act unsupervised.

## What has to change in the architecture

Honestly assessed, because this is where the cost is:

- **The idle loop must think without being asked.** Today `idle means idle` —
  no generation without a command, deliberately. Proactivity breaks that, and it
  is a real cost: a local model waking on a timer burns battery and heat on a
  laptop. Mitigation: think on *events* (context changed, a rule fired, a task
  finished), never on a bare timer.
- **The observer becomes load-bearing.** It currently reports the frontmost app.
  Anything interesting needs more, and more observation is more exposure — the
  journal already keeps everything forever in plain text. A proactive Zero
  watching more, remembering more, and now *talking*, is a different privacy
  object than a thing that answers questions. That deserves a retention policy
  before it deserves features.
- **Delivery is a new dependency.** Reaching your phone means a channel that can
  fail: push, a bridge, or a message. Every delivery path is a way to be wrong
  loudly, and offline behaviour has to be designed (hold and deliver later, or
  drop) rather than discovered.
- **Scheduling is the honest first step.** The old Zero had
  `scheduled_tasks.json` and the new one has nothing. A rule you wrote firing at
  a time you chose is proactivity with the judgment removed — all of the value,
  none of the trust problem. It is also the thing that most reduces trips to the
  computer, which is the only metric that matters.

## What not to build

- **No level-2 notification for anything Zero judged by itself**, until there is
  a precision record that says it may.
- **No "smart" salience early.** Rules you wrote first; learned judgment much
  later, from the shadow log as training data.
- **No proactivity before approve mode.** An agent that both acts on its own
  judgment *and* speaks on its own judgment, before either has been earned, is
  two unproven systems compounding.
- **No unbounded watching.** Every new thing the observer notices should be
  justified by something Zero can then do or say about it.

## The order

1. **Reporting** — async "that's done" through the existing answer channel.
   Small, and it makes long tasks possible.
2. **Scheduling** — your rules, your times. The biggest reduction in
   computer-time available to us, with no judgment risk.
3. **`quiet` shadow log** — Zero starts forming opinions about when to speak,
   into a file that never reaches you. Costs nothing, teaches everything.
4. **Read the log, measure precision, and only then decide** whether initiating
   is worth building at all.

Step 4 may conclude that it isn't, and that scheduling plus level-0 presence is
the whole product. That would be a good outcome, not a failed one.
