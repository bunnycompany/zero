# her/presence.py
#
# Presence: the line that is already there when you look. Level 0 of the
# loudness ladder in docs/proactivity.md — Her never pings; she is present.
#
# Two things live here, kept deliberately separate:
#
#   * refresh()/tick() — rewrite namespace/her/presence/current from what is
#     already known (facts, the clock, the schedule, the journal, the agent's
#     own health). No model call, ever. A file rewrite on events only.
#
#   * would_say() — Her forms an opinion that she would speak up now. In
#     `quiet` (the default, and where a fresh install stays) that opinion goes
#     into her/unsent.ndjson and nowhere else. This is shadow mode for speech:
#     you read the list later and say, line by line, "would I have wanted
#     this?" Only a human moves the level (namespace/control/presence), and
#     `live` additionally demands a precision record — a vibe is not enough.
#
# Triggers are rules, not judgment: a date you told her about is near, a
# thing you keep asking for, a reminder you set that is about to fire, or a
# part of her that has stopped. Learned salience is not built, on purpose.

import platform
import re
import subprocess
import time
import uuid

from her import intake
from zero import memory, ns, nspath, scheduler

CHANNEL = "her/presence"
LEVELS = ("quiet", "digest", "ambient", "live")
DEFAULT_LEVEL = "quiet"

GLANCE_CHARS = 40          # a lens or a Glyph shows one short line
DATE_HORIZON_DAYS = 7      # "a week ahead, nowhere else" — the intake ack promises it
REPEAT_ASK_MIN = 3         # the same ask this many times is a pattern
SCHEDULE_HORIZON_S = 3600  # a reminder firing within the hour is worth a line
OBSERVER_STALE_S = 120.0   # context older than this means the watcher died
LIVE_MIN_REVIEWED = 20     # live needs a record, not a vibe
LIVE_MIN_PRECISION = 0.8
DEDUP_WINDOW_S = 86400     # one opinion per key per day


# --- the ladder --------------------------------------------------------------

def level():
    """Human-written, read every time, never cached. Unknown fails to quiet."""
    lv = ns.read_text("presence_level", default=DEFAULT_LEVEL).lower()
    return lv if lv in LEVELS else DEFAULT_LEVEL


def precision():
    """(reviewed, wanted_fraction) over the human's verdicts in unsent.ndjson."""
    verdicts = [e for e in ns.read_lines(nspath.her_unsent()) if e.get("event") == "verdict"]
    if not verdicts:
        return 0, 0.0
    latest = {}
    for v in verdicts:  # a later verdict on the same entry wins
        latest[v.get("review_of")] = bool(v.get("wanted"))
    n = len(latest)
    return n, sum(1 for w in latest.values() if w) / n


def delivery_level():
    """The level Her actually delivers at. `live` without a precision record
    degrades to `ambient` — Her cannot talk her way up, and neither can a
    setting with no evidence behind it."""
    lv = level()
    if lv == "live":
        n, p = precision()
        if n < LIVE_MIN_REVIEWED or p < LIVE_MIN_PRECISION:
            return "ambient"
    return lv


# --- the unsent log ----------------------------------------------------------

def entries():
    return [e for e in ns.read_lines(nspath.her_unsent()) if e.get("event") == "would_say"]


def _delivered_ids():
    return {e.get("entry") for e in ns.read_lines(nspath.her_unsent()) if e.get("event") == "delivered"}


def _reviewed_ids():
    return {e.get("review_of") for e in ns.read_lines(nspath.her_unsent()) if e.get("event") == "verdict"}


def unreviewed():
    seen = _reviewed_ids()
    return [e for e in entries() if e.get("id") not in seen]


def would_say(text, trigger, key, evidence="", now=None):
    """Record that Her would speak now. Deduplicated per key per day. Returns
    the entry id, or None if this opinion was already on record."""
    now = time.time() if now is None else now
    for e in entries():
        if e.get("key") == key and now - e.get("ts", 0) < DEDUP_WINDOW_S:
            return None
    eid = uuid.uuid4().hex[:10]
    ns.append_line(nspath.her_unsent(), "her", event="would_say", id=eid, text=text,
                   trigger=trigger, key=key, evidence=evidence, level=level())
    ns.log("her", "would_say", id=eid, trigger=trigger, level=level())
    return eid


def review(entry_id, wanted):
    """A human's verdict on one unsent line. Append-only, like everything."""
    ns.append_line(nspath.her_unsent(), "human", event="verdict", review_of=entry_id,
                   wanted=bool(wanted))


def _mark_delivered(entry_id, how):
    ns.append_line(nspath.her_unsent(), "her", event="delivered", entry=entry_id, how=how)
    ns.log("her", "delivered", id=entry_id, how=how)


# --- triggers (rules you can read) ------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_WORDS = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b"
    r"|\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE)


def _dates_in(text):
    """[(month, day)] mentioned in free text, e.g. 'Theo 14 March', 'Sept 3'."""
    out = []
    for m in _DATE_WORDS.finditer(text):
        if m.group(1):
            mon, day = m.group(1)[:3].lower(), int(m.group(2))
        else:
            day, mon = int(m.group(3)), m.group(4)[:3].lower()
        if mon in _MONTHS and 1 <= day <= 31:
            out.append((_MONTHS[mon], day))
    return out


def _days_until(month, day, now):
    lt = time.localtime(now)
    for year in (lt.tm_year, lt.tm_year + 1):
        try:
            target = time.mktime((year, month, day, 0, 0, 0, 0, 0, -1))
        except (OverflowError, ValueError):
            return None
        today = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        d = round((target - today) / 86400)
        if d >= 0:
            return d
    return None


def _when_phrase(days):
    return {0: "today", 1: "tomorrow"}.get(days, f"in {days} days")


def date_triggers(now):
    out = []
    for f in memory.load_facts():
        if f.get("subject") != "dates" and not str(f.get("origin", "")).startswith("intake:dates"):
            continue
        for month, day in _dates_in(f.get("text", "")):
            d = _days_until(month, day, now)
            if d is None or d > DATE_HORIZON_DAYS:
                continue
            said = f["text"].split(":", 1)[-1].strip()
            out.append((f"You told me: “{said}” — that's {_when_phrase(d)}.",
                        "date", f"date:{month:02d}-{day:02d}:{time.localtime(now).tm_year}",
                        f"fact {f.get('id')}"))
    return out


def _norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def repeat_triggers(now):
    counts = {}
    for e in ns.read_journal():
        if e.get("event") == "command_received" and e.get("source", "human") == "human":
            key = _norm(e.get("text", ""))
            if key:
                counts[key] = counts.get(key, 0) + 1
    out = []
    for key, n in counts.items():
        if n >= REPEAT_ASK_MIN:
            out.append((f"You've asked me to “{key}” {n} times now — want me to keep that ready for you?",
                        "repeat", f"repeat:{key}", f"{n} organic asks"))
    return out


def schedule_triggers(now):
    out = []
    for t in scheduler._load():
        if t.get("done"):
            continue
        dt = t.get("at", 0) - now
        if 0 <= dt <= SCHEDULE_HORIZON_S:
            mins = max(1, int(dt // 60))
            out.append((f"In about {mins} minute{'s' if mins != 1 else ''} I'll bring up “{t['text']}”.",
                        "schedule", f"sched:{t.get('id')}:{t.get('at')}", "task you set"))
    return out


def triggers(now=None):
    now = time.time() if now is None else now
    out = []
    for fn in (date_triggers, repeat_triggers, schedule_triggers):
        try:
            out.extend(fn(now))
        except Exception:
            continue  # one broken rule must not silence the others
    return out


# --- degraded-mode honesty (US-047) ------------------------------------------

def observer_down(now=None):
    """True only when the watcher once spoke and has since gone quiet."""
    now = time.time() if now is None else now
    doc = ns.read_doc("context")
    return bool(doc) and now - doc.get("ts", now) > OBSERVER_STALE_S


# --- composing the line ------------------------------------------------------

def user_name():
    for f in memory.load_facts():
        if f.get("origin") == "intake:name":
            return f["text"].replace("Wants to be called", "").strip()
    return ""


def _greeting(now):
    h = time.localtime(now).tm_hour
    if 5 <= h < 12:
        return "Morning"
    if 12 <= h < 18:
        return "Afternoon"
    if 18 <= h < 23:
        return "Evening"
    return "Still up"


def _glance(text):
    text = " ".join(text.split())
    return text if len(text) <= GLANCE_CHARS else text[:GLANCE_CHARS - 1].rstrip() + "…"


def _deliverable(now):
    """The one unsent entry Her may surface at the current level, or None."""
    lv = delivery_level()
    if lv == "quiet":
        return None
    delivered = _delivered_ids()
    fresh = [e for e in entries() if e["id"] not in delivered and now - e.get("ts", 0) < DEDUP_WINDOW_S]
    if not fresh:
        return None
    if lv == "digest":
        recent = [e for e in ns.read_lines(nspath.her_unsent())
                  if e.get("event") == "delivered" and now - e.get("ts", 0) < 86400]
        if recent:
            return None  # one a day, and today's is spent
    return fresh[-1]


def _notify(text):
    """Level 2, macOS only, live only. Best-effort: never raises."""
    if platform.system() != "Darwin":
        return False
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification {_osa(text)} with title "Her"'],
                       timeout=5, capture_output=True, stdin=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _osa(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def compose(now=None):
    """Build the presence payload. Pure over the namespace; writes nothing
    except the intake question it may open (that is the asking surface)."""
    now = time.time() if now is None else now
    for text, trigger, key, evidence in triggers(now):
        would_say(text, trigger, key, evidence, now=now)

    name = user_name()
    head = f"{_greeting(now)}{', ' + name if name else ''}."
    parts = [head]
    attention = False
    glance = "quiet"
    item = None

    if observer_down(now):
        parts.append("The part of me that watches the screen has stopped — I can still hear you.")
        glance = "watcher down · I can hear you"

    item = _deliverable(now)
    if item:
        parts.append(item["text"])
        glance = item["text"]
        attention = delivery_level() in ("ambient", "live")
    elif not observer_down(now):
        parts.append("Nothing needs you.")

    q = intake.next_question(now)
    if q:
        parts.append("One question when you have a moment.")
        if glance == "quiet":
            glance = "quiet · one question for you"

    answered, total = intake.progress()
    return {
        "line": " ".join(parts),
        "glance": _glance(glance),
        "state": ns.read_text("status", default="idle"),
        "question": {"id": q["id"], "text": q["ask"]} if q else None,
        "attention": attention,
        "item": item["id"] if item else None,
        "level": level(),
        "delivery": delivery_level(),
        "intake": {"answered": answered, "total": total},
        "unsent_unreviewed": len(unreviewed()),
    }


def refresh(reason="event", now=None):
    """Recompute and write the presence doc if anything changed. Delivery of
    an unsent line (digest/ambient/live) is recorded here, once, so a line
    that reached you can be told apart from one that never did."""
    now = time.time() if now is None else now
    payload = compose(now)
    payload["reason"] = reason
    prev = ns.read_doc(CHANNEL)
    prev_payload = dict(prev["payload"]) if prev and isinstance(prev.get("payload"), dict) else {}
    prev_payload.pop("reason", None)
    cmp = dict(payload)
    cmp.pop("reason", None)
    if cmp != prev_payload:
        ns.write_doc(CHANNEL, "her", payload)
        if payload["item"] and payload["item"] not in _delivered_ids():
            how = payload["delivery"]
            if how == "live" and _notify(_glance(payload["line"])):
                how = "live+notification"
            _mark_delivered(payload["item"], how)
    return payload


def tick(now=None):
    """Idle heartbeat hook: a file rewrite on a timer is fine; a model call
    on a timer would not be (idle means idle)."""
    return refresh("heartbeat", now=now)


def current():
    doc = ns.read_doc(CHANNEL)
    return doc["payload"] if doc else None
