# her/intake.py
#
# Getting to know you — the "human in the box" process, paced like a person
# would pace it: one question at a time, a few a day, never a form.
#
# Design rules (each one is what keeps Her from being wrong about you):
#   1. The questions are scripted, not generated. Her cannot invent a question
#      that presumes something about you.
#   2. Your answer is stored verbatim as a fact, tagged with which question it
#      answered. The model may extract extra facts from it, but the primary
#      record is your own words.
#   3. Skipping is free and remembered. "never" retires the question for good.
#   4. Her asks by leaving the question in her/presence — she never interrupts.
#      You answer when you look. Level 0 of the loudness ladder.
#
# State: namespace/her/intake/current (writer: her).

import time

from zero import memory, ns

PACE_PER_DAY = 3           # questions Her will open in one day
SKIP_RETRY_S = 7 * 86400   # a skipped question comes back once, a week later

# id, what Her asks, the fact template ({a} = your verbatim answer), subject,
# importance, and how Her acknowledges it. Order is the conversation.
DECK = [
    {"id": "name", "ask": "What should I call you?",
     "fact": "Wants to be called {a}", "subject": "name", "importance": 10,
     "ack": "Got it — {a} it is."},
    {"id": "her_name", "ask": "And what would you like to call me? Her is fine, or pick anything.",
     "fact": "Calls their assistant {a}", "subject": "assistant_name", "importance": 8,
     "ack": "{a}. I like it."},
    {"id": "tone", "ask": "How do you like to be talked to — short and plain, or warmer and chattier?",
     "fact": "How they like to be spoken to: {a}", "subject": "tone", "importance": 9,
     "ack": "Noted, in your words: “{a}”."},
    {"id": "rhythm", "ask": "When does your day usually start, and when does it wind down?",
     "fact": "Their day: {a}", "subject": "rhythm", "importance": 7,
     "ack": "Thanks — I'll keep to that rhythm and stay quiet outside it."},
    {"id": "people", "ask": "Who are the people you'd want me to know by name — family, a partner, close friends?",
     "fact": "People who matter to them: {a}", "subject": "people", "importance": 9,
     "ack": "I've written those names down exactly as you said them."},
    {"id": "work", "ask": "What are you working on, or looking after, these days?",
     "fact": "What they're working on: {a}", "subject": "projects", "importance": 8,
     "ack": "Thank you. That's the kind of thing I'll try to be useful for."},
    {"id": "dates", "ask": "Any dates that matter — birthdays, anniversaries, a deadline — you'd want me to keep track of?",
     "fact": "Dates that matter: {a}", "subject": "dates", "importance": 9,
     "ack": "Kept. I'll bring those up a week ahead, nowhere else."},
    {"id": "notice", "ask": "What would you want me to notice for you, if I could? And what should I never look at?",
     "fact": "What to notice, and what never to look at: {a}", "subject": "boundaries", "importance": 10,
     "ack": "Understood. The “never” part is a rule for me, not a preference."},
    {"id": "worry", "ask": "What's one thing you keep forgetting or worrying about that I could take off your mind?",
     "fact": "Something they keep forgetting or worrying about: {a}", "subject": "worries", "importance": 8,
     "ack": "I'll carry that one for you."},
    {"id": "devices", "ask": "Which of your things should I live on — this Mac, your phone, your glasses? I only go where you say.",
     "fact": "Where Her may live: {a}", "subject": "devices", "importance": 7,
     "ack": "Then that's where I'll be, and nowhere else. Pair one with  her pair  whenever you like."},
]
_BY_ID = {q["id"]: q for q in DECK}

SKIP_WORDS = {"skip", "pass", "later", "not now", "next", "no thanks", "nah", "maybe later"}
RETIRE_WORDS = {"never", "don't ask", "dont ask", "stop asking", "never ask", "no"}

CHANNEL = "her/intake"


def _empty():
    return {"started": time.time(), "asked": {}, "answered": {}, "skipped": {}, "retired": []}


def load():
    doc = ns.read_doc(CHANNEL)
    if not doc or not isinstance(doc.get("payload"), dict):
        return _empty()
    state = _empty()
    state.update(doc["payload"])
    return state


def _save(state):
    ns.write_doc(CHANNEL, "her", state)


def question(qid):
    return _BY_ID.get(qid)


def _eligible(state, q, now):
    qid = q["id"]
    if qid in state["answered"] or qid in state["retired"]:
        return False
    skipped_at = state["skipped"].get(qid)
    if skipped_at is not None and now - skipped_at < SKIP_RETRY_S:
        return False
    return True


def pending(state=None):
    """The question Her has opened and you have not yet answered, or None."""
    state = state or load()
    for qid, ts in state["asked"].items():
        if qid not in state["answered"] and qid not in state["retired"] \
                and state["skipped"].get(qid, -1) < ts:
            return _BY_ID.get(qid)
    return None


def _asked_today(state, now):
    day_ago = now - 86400
    return sum(1 for ts in state["asked"].values() if ts > day_ago)


def next_question(now=None):
    """Open the next question if pace allows. Idempotent: while one is
    pending, the same one is returned and nothing new opens. Returns the
    question dict or None (nothing left, or enough for today)."""
    now = time.time() if now is None else now
    state = load()
    p = pending(state)
    if p:
        return p
    if _asked_today(state, now) >= PACE_PER_DAY:
        return None
    for q in DECK:
        if _eligible(state, q, now):
            state["asked"][q["id"]] = now
            _save(state)
            ns.log("her", "intake_asked", question=q["id"])
            return q
    return None


def handles(cmd):
    """True if this command is an answer to a Her question. Only commands
    that say so (reply_to) are intercepted — a plain `zero ...` ask never is,
    so Her can never swallow a real request by guessing."""
    return isinstance(cmd, dict) and cmd.get("reply_to") in _BY_ID


def progress():
    state = load()
    return len(state["answered"]), len(DECK)


def turn(cmd, brain=None, now=None):
    """Record one answer and return what Her says back. Deterministic: the
    acknowledgement quotes you, and the next question (if any) is scripted.
    The model only ever gets to extract *additional* facts from your words."""
    now = time.time() if now is None else now
    qid = cmd["reply_to"]
    q = _BY_ID[qid]
    text = (cmd.get("text") or "").strip()
    state = load()
    low = text.lower().strip(" .!")

    if not text or low in SKIP_WORDS:
        state["skipped"][qid] = now
        _save(state)
        ns.log("her", "intake_skipped", question=qid)
        reply = "No problem — I'll leave that one for now."
    elif low in RETIRE_WORDS:
        if qid not in state["retired"]:
            state["retired"].append(qid)
        _save(state)
        ns.log("her", "intake_retired", question=qid)
        reply = "Understood. I won't ask that again."
    else:
        state["answered"][qid] = {"ts": now, "text": text}
        _save(state)
        # your words, verbatim, are the fact — the model never gets to
        # paraphrase what you told Her about yourself
        memory.submit_observation(
            q["fact"].format(a=text), q["subject"], q["importance"],
            origin=f"intake:{qid}", speaker="user",
        )
        ns.log("her", "intake_answered", question=qid, chars=len(text))
        # optional extras (names inside "people", dates inside "dates"): the
        # brain proposes, the same queue and consolidator decide
        if brain is not None and hasattr(brain, "extract_observations"):
            try:
                brain.extract_observations(f"{q['ask']} — {text}", None, None)
            except Exception:
                pass  # extraction is a bonus, never a reason to fail the turn
        reply = q["ack"].format(a=text)

    nxt = next_question(now)
    if nxt:
        reply = f"{reply} {nxt['ask']}"
    else:
        answered, total = progress()
        if answered >= total:
            reply = f"{reply} That's everything I wanted to ask. From here on I just listen."
        elif _asked_today(load(), now) >= PACE_PER_DAY:
            reply = f"{reply} That's enough questions for today — I'll have one more tomorrow."
    return reply


def summary():
    """Plain-English one-liner for `her status`."""
    answered, total = progress()
    p = pending()
    if answered >= total:
        return "Her knows what you chose to tell her; no more questions."
    if p:
        return f"{answered} of {total} questions answered — one is waiting for you."
    return f"{answered} of {total} questions answered."
