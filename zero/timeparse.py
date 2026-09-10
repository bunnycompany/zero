# zero/timeparse.py
#
# Natural-language times for the scheduler (US-021). One pure function:
#
#     parse(text, now) -> (at_unix | None, every_seconds | None, remaining_text)
#
# "in 2h", "in 30 min", "in an hour", "at 6", "at 6pm", "at 18:30", "at noon",
# "at midnight", "tomorrow at 9", "tomorrow morning", "tonight", "this evening",
# "on thursday", "next monday at 10", "every day at 8", "every morning",
# "every weekday at 9" (approximated as daily, with a note), "every 2 hours".
#
# Rules, stated once:
#   - an hour with no am/pm and no day word is the *next* occurrence: "at 6"
#     is 18:00 when it is 09:00 and 06:00 when it is 20:00;
#   - an hour with no am/pm on a named day (tomorrow, thursday, every day)
#     is daytime: 7-11 are morning, 12 is noon, 1-6 are afternoon/evening;
#   - a day word with no clock gets a default: morning 09:00 (08:00 when
#     recurring), afternoon 15:00, evening 18:00, night/tonight 20:00,
#     a bare day 09:00;
#   - when a phrase appears twice ("look at 3 files at 6") the last one is
#     the time, because that is where people put it.
#
# Wall-clock arithmetic goes through time.localtime / time.mktime with
# tm_isdst = -1, so "tomorrow at 9" is 09:00 on the wall even across a DST
# change, while "in 24h" is exactly 86400 seconds. No dependencies.

import re
import time
from dataclasses import dataclass

DAY = 86400
WEEK = 7 * DAY

_WORD_NUM = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty-five": 45, "fifty": 50, "sixty": 60,
}
_NUM = r"(?:\d+|" + "|".join(sorted(_WORD_NUM, key=len, reverse=True)) + r")"
_HOUR_WORDS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"

_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": DAY, "day": DAY, "days": DAY,
    "w": WEEK, "wk": WEEK, "wks": WEEK, "week": WEEK, "weeks": WEEK,
}
_UNIT = r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|wks?|[smhdw])"

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WD_FULL = "|".join(_WEEKDAYS)
_WD_ANY = _WD_FULL + "|mon|tues|tue|wed|thurs|thur|thu|fri|sat|sun"
_WD_INDEX = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "wednes": 2, "thu": 3, "thur": 3,
             "thurs": 3, "fri": 4, "sat": 5, "satur": 5, "sun": 6}

# day-part defaults (hour): one-shot, and recurring ("every morning" is 08:00)
_PARTS = {"morning": 9, "afternoon": 15, "evening": 18, "night": 20}
_PARTS_EVERY = {"morning": 8, "afternoon": 15, "evening": 18, "night": 20}
_PART = r"(?:morning|afternoon|evening|night)"

_RE_EVERY_N = re.compile(r"\b(?:every|each)\s+(" + _NUM + r")\s*(" + _UNIT + r")\b", re.I)
_RE_EVERY_WORD = re.compile(
    r"\b(?:every|each)\s+(hour|minute|day|week|weekday|weekdays|" + _PART + r"|" + _WD_ANY + r")s?\b"
    r"(?:\s+(" + _PART + r")\b)?", re.I)
_RE_EVERY_ADV = re.compile(r"\b(hourly|daily|weekly)\b", re.I)
_RE_IN = re.compile(r"\bin\s+(half\s+an?|" + _NUM + r")\s*(" + _UNIT + r")\b", re.I)
# groups: 1 tonight | 2 prefix 3 weekday | 4 bare full weekday | 5 today/tomorrow 6 part | 7 trailing part
_RE_DAY = re.compile(
    r"\b(?:(tonight)\b"
    r"|(on|next|this)\s+(" + _WD_ANY + r")\b"
    r"|(" + _WD_FULL + r")\b"
    r"|(today|tomorrow|this)\b)"
    r"(?:\s+(" + _PART + r")\b)?()", re.I)
# groups: 1 noon/midnight | 2 h 3 m 4 am/pm | 5 h 6 m (colon) | 7 "at" h 8 in-the-part 9 at-night | 10 h o'clock
_RE_CLOCK = re.compile(
    r"(?:\bat\s+)?\b(noon|midday|midnight)\b"
    r"|(?:\bat\s+)?\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?![a-z])"
    r"|(?:\bat\s+)?\b(\d{1,2}):(\d{2})\b"
    r"|\bat\s+(\d{1,2}|" + _HOUR_WORDS + r")\b(?:\s*o'?clock\b)?"
    r"(?:\s+in\s+the\s+(morning|afternoon|evening)\b|\s+at\s+(night)\b)?"
    r"|\b(\d{1,2}|" + _HOUR_WORDS + r")\s*o'?clock\b",
    re.I)


@dataclass
class Parsed:
    at: float = None            # unix seconds, or None when no time was found
    every: int = None           # seconds between fires, or None for one-shot
    remaining: str = ""         # the text with every time phrase removed
    relative: bool = False      # came from "in …" (for describe())
    note: str = ""              # a plain-words caveat, e.g. weekday approximation


# ---- wall-clock helpers ---------------------------------------------------

def _local(now):
    return time.localtime(now)


def _wall(now, days_ahead, hour, minute):
    """Unix time of hour:minute on the local day `days_ahead` days from now.
    Day overflow and DST are left to the C library (tm_isdst = -1)."""
    lt = _local(now)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + days_ahead,
                        hour, minute, 0, 0, 0, -1))


def _days_between(now, at):
    """Whole local calendar days from now's date to at's date."""
    a, b = _local(now), _local(at)
    da = time.mktime((a.tm_year, a.tm_mon, a.tm_mday, 12, 0, 0, 0, 0, -1))
    db = time.mktime((b.tm_year, b.tm_mon, b.tm_mday, 12, 0, 0, 0, 0, -1))
    return int(round((db - da) / DAY))


def _num(s):
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    return _WORD_NUM.get(s, 0)


def _unit(s):
    return _UNITS[s.strip().lower()]


def _weekday_index(word):
    w = word.lower()
    if w.endswith("day"):
        w = w[:-3]
    return _WD_INDEX[w]


# ---- the parse ------------------------------------------------------------

def _last(regex, text):
    found = None
    for found in regex.finditer(text):
        pass
    return found


def _cut(text, span):
    return text[:span[0]] + " " + text[span[1]:]


def _clean(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[\s,.;:\-–—]+|[\s,.;:\-–—]+$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _resolve_clock(m):
    """-> (hour, minute, explicit) from a _RE_CLOCK match, or None.
    `explicit` is True when am/pm, a 24h clock or noon/midnight settled it."""
    g = m.groups()
    if g[0]:
        return (0 if g[0].lower() == "midnight" else 12, 0, True)
    if g[1]:
        h, mi, ap = int(g[1]), int(g[2] or 0), g[3].lower().replace(".", "")
        if h > 12 or h == 0 or mi > 59:
            return None
        return (h % 12 + (12 if ap == "pm" else 0), mi, True)
    if g[4]:
        h, mi = int(g[4]), int(g[5])
        if h > 23 or mi > 59:
            return None
        # "07:15" is a 24h clock; "7:15" is as ambiguous as "at 7"
        return (h, mi, h > 12 or h == 0 or g[4].startswith("0"))
    word = g[6] or g[9]
    h = _num(word)
    if h > 23:
        return None
    part = (g[7] or g[8] or "").lower()
    if part:
        if part == "morning":
            h = 0 if h == 12 else h
        elif h < 12:
            h += 12
        return (h, 0, True)
    return (h, 0, h > 12 or h == 0)


def _daytime(h):
    """Ambiguous 1..12 on a named day: 7-11 morning, 12 noon, 1-6 evening."""
    return 12 if h == 12 else (h + 12 if h <= 6 else h)


def _next_today(now, h, mi):
    """Ambiguous 1..12 today: the next occurrence, morning or evening."""
    cands = sorted({h % 12, h % 12 + 12})
    for hh in cands:
        t = _wall(now, 0, hh, mi)
        if t > now:
            return t
    return _wall(now, 1, cands[0], mi)


def parse_full(text, now):
    """Like parse() but returns a Parsed with relative/note for describe()."""
    p = Parsed(remaining=_clean(text))
    src = text
    every = None
    every_part = None
    every_wd = None
    note = ""

    m = _RE_EVERY_N.search(src)
    if m:
        every = _num(m.group(1)) * _unit(m.group(2))
        src = _cut(src, m.span())
    else:
        m = _RE_EVERY_WORD.search(src)
        if m:
            w = m.group(1).lower()
            if w in ("hour", "minute", "day", "week"):
                every = {"hour": 3600, "minute": 60, "day": DAY, "week": WEEK}[w]
            elif w in ("weekday", "weekdays"):
                every = DAY
                note = "weekends included for now"
            elif w in _PARTS:
                every, every_part = DAY, w
            else:
                every, every_wd = WEEK, _weekday_index(w)
            if m.group(2):
                every_part = m.group(2).lower()
            src = _cut(src, m.span())
        else:
            m = _RE_EVERY_ADV.search(src)
            if m:
                every = {"hourly": 3600, "daily": DAY, "weekly": WEEK}[m.group(1).lower()]
                src = _cut(src, m.span())

    delay = None
    m = _last(_RE_IN, src)
    if m:
        n = m.group(1).lower()
        delay = (0.5 if n.startswith("half") else _num(n)) * _unit(m.group(2))
        src = _cut(src, m.span())

    day_ahead = None       # int days from today
    day_part = None
    weekday = None
    weekday_next = False
    m = _last(_RE_DAY, src)
    if m:
        tonight, prefix, wd, wd_full, rel, part, _ = m.groups()
        part = (part or "").lower() or None
        if tonight:
            day_ahead, day_part = 0, "night"
        elif wd or wd_full:
            weekday = _weekday_index(wd or wd_full)
            weekday_next = (prefix or "").lower() == "next"
            day_part = part
        elif rel.lower() == "this" and not part:
            m = None    # "this" alone means nothing
        else:
            day_ahead = 1 if rel.lower() == "tomorrow" else 0
            day_part = part
        if m:
            src = _cut(src, m.span())

    clock = None
    m = _last(_RE_CLOCK, src)
    if m:
        clock = _resolve_clock(m)
        if clock:
            src = _cut(src, m.span())

    p.remaining = _clean(src)
    p.note = note

    if every is not None:
        p.every = int(every)
        part = every_part or day_part
        if clock:
            h, mi, explicit = clock
            h = h if explicit else _daytime(h)
        elif part:
            h, mi = _PARTS_EVERY[part], 0
        else:
            h = None
        wd = every_wd if every_wd is not None else weekday
        if h is None and wd is None:
            p.at = now + p.every
            return p
        if h is None:
            h, mi = _PARTS_EVERY["morning"], 0
        ahead = 0 if wd is None else (wd - _local(now).tm_wday) % 7
        step = 7 if wd is not None else 1
        t = _wall(now, ahead, h, mi)
        while t <= now:
            ahead += step
            t = _wall(now, ahead, h, mi)
        p.at = t
        return p

    if delay is not None:
        p.at = now + delay
        p.relative = True
        return p

    if weekday is not None:
        day_ahead = (weekday - _local(now).tm_wday) % 7
        if weekday_next and day_ahead == 0:
            day_ahead = 7

    if day_ahead is None and clock is None:
        return p     # nothing we understood

    if clock:
        h, mi, explicit = clock
        if day_ahead is None:
            t = _wall(now, 0, h, mi) if explicit else _next_today(now, h, mi)
            p.at = t if t > now else _wall(now, 1, h, mi)
            return p
        if not explicit:
            h = _daytime(h)
        t = _wall(now, day_ahead, h, mi)
        if t <= now:
            t = _wall(now, day_ahead + (7 if weekday is not None else 1), h, mi)
        p.at = t
        return p

    h = _PARTS[day_part or "morning"]
    t = _wall(now, day_ahead, h, 0)
    if t <= now:
        if weekday is not None:
            t = _wall(now, day_ahead + 7, h, 0)
        else:
            t = now + 60      # "tonight" said at 23:00: soon, and say so
            p.relative = True
    p.at = t
    return p


def parse(text, now):
    """-> (at_unix | None, every_seconds | None, remaining_text)."""
    p = parse_full(text, now)
    return p.at, p.every, p.remaining


# ---- saying it back in plain words ---------------------------------------

def _clock_words(h, mi):
    if h == 0 and mi == 0:
        return "midnight"
    if h == 12 and mi == 0:
        return "noon"
    hh = h % 12 or 12
    return f"{hh}" if mi == 0 else f"{hh}:{mi:02d}"


def _part_words(h):
    if h < 12:
        return "morning"
    if h < 17:
        return "afternoon"
    if h < 20:
        return "evening"
    return "night"


def _span_words(secs):
    secs = int(round(secs))
    for unit, name in ((WEEK, "week"), (DAY, "day"), (3600, "hour"), (60, "minute")):
        if secs >= unit and secs % unit == 0:
            n = secs // unit
            if n == 1:
                return "an hour" if name == "hour" else f"a {name}"
            return f"{n} {name}s"
    if secs >= 60:
        n = secs // 60
        return "a minute" if n == 1 else f"{n} minutes"
    return f"{secs} seconds"


def _at_words(lt):
    """'at 8 in the morning' / 'at noon' / 'at 9 at night' for a recurrence."""
    clock = _clock_words(lt.tm_hour, lt.tm_min)
    if clock in ("noon", "midnight"):
        return f"at {clock}"
    part = _part_words(lt.tm_hour)
    return f"at {clock} " + ("at night" if part == "night" else f"in the {part}")


def _day_name(lt):
    return _WEEKDAYS[lt.tm_wday].capitalize()


def describe(at, every, now, relative=False, note=""):
    """A phrase that finishes 'I will bring it up …'."""
    if every:
        lt = _local(at)
        if every == DAY:
            base = "every day " + _at_words(lt)
        elif every == WEEK:
            base = f"every {_day_name(lt)} " + _at_words(lt)
        else:
            span = _span_words(every)
            base = "every " + re.sub(r"^an? ", "", span)
        return base + (f", {note}" if note else "")

    if relative:
        return "in " + _span_words(at - now)

    lt = _local(at)
    clock = _clock_words(lt.tm_hour, lt.tm_min)
    d = _days_between(now, at)
    part = _part_words(lt.tm_hour)
    date = time.strftime("%-d %B", lt)
    day = f"on {_day_name(lt)}" if d <= 6 else f"next {_day_name(lt)}" if d == 7 else f"on {date}"
    if clock == "noon":
        when = "today" if d == 0 else "tomorrow" if d == 1 else day
        return f"at noon {when}"
    if clock == "midnight":
        return "at midnight tonight" if d <= 1 else f"at midnight {day}"
    if d == 0:
        slot = "tonight" if part == "night" else f"this {part}"
    elif d == 1:
        slot = f"tomorrow {part}"
    elif d <= 7:
        slot = f"{day} {part}"
    else:
        slot = f"on {date} " + ("at night" if part == "night" else f"in the {part}")
    return f"at {clock} {slot}"
