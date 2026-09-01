# her/profile.py
#
# The pinned profile block: what Her knows about you, in your own words,
# rendered into namespace/memory/core/current so every decision and every
# answer sees it first. Cite or abstain, made mechanical: only facts with an
# `intake:` origin (things you typed in answer to a question) are eligible,
# each line says when you said it, and nothing is paraphrased.
#
# The consolidator owns memory/core (namespace/README.md); this module only
# renders text. Hard cap ~800 tokens.

import time

from zero import memory

CORE_CAP_CHARS = 3200
HEADER = "What you know about this person, in their own words:"


def _when(ts):
    try:
        return time.strftime("%-d %b %Y", time.localtime(ts))
    except Exception:
        return "unknown date"


def render(facts=None):
    """Return the core block text, or '' when there is nothing you said."""
    facts = memory.load_facts() if facts is None else facts
    said = [f for f in facts if str(f.get("origin", "")).startswith("intake:")]
    if not said:
        return ""
    said.sort(key=lambda f: f.get("ts_observed", 0))
    lines = [HEADER]
    used = len(HEADER)
    for f in said:
        line = f"- {f['text']} (said {_when(f.get('ts_observed', 0))})"
        if used + len(line) + 1 > CORE_CAP_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def facts_for_display():
    """Every live fact Her keeps, oldest first, for `her profile`."""
    return sorted(memory.load_facts(), key=lambda f: f.get("ts_observed", 0))
