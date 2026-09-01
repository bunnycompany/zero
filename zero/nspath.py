# zero/nspath.py
#
# Single source of truth for where the Zero root and namespace live.
# Resolution order: $ZERO_ROOT env var -> .zero-root marker walk-up -> repo parent.
# Paths are resolved at call time so tests can point ZERO_ROOT at a sandbox.
# No other module may spell an absolute path to the namespace.

import os
from pathlib import Path


def root() -> Path:
    env = os.environ.get("ZERO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".zero-root").exists():
            return parent
    return here.parents[1]


def ns() -> Path:
    return root() / "namespace"


# state channels: exactly one writer each (enforced in ns.OWNERS)
#   status     agent loop heartbeat: idle | thinking | executing | error
#   context    what the observer sees (JSON doc)
#   action     last decision the brain emitted (JSON doc, display only)
#   checkpoint executor durability record (JSON doc)
#   mode       shadow | approve | live — written by HUMANS only, never code

#   presence_level  quiet | digest | ambient | live — Her's speech ladder,
#              written by HUMANS only (namespace/control/presence), never code

def state(channel: str) -> Path:
    if channel == "mode":
        return ns() / "control" / "mode"
    if channel == "presence_level":
        return ns() / "control" / "presence"
    return ns() / channel / "current"


# command queue: UI/CLI -> agent, one file per submission, claim-by-rename
def inbox() -> Path:
    return ns() / "command" / "inbox"


def done() -> Path:
    return ns() / "command" / "done"


# append-only journal: 'current' files answer "what now", only this answers
# "what happened"
def journal() -> Path:
    return ns() / "log" / "journal.ndjson"


# memory channels (see namespace/README.md): observations queue in,
# consolidated facts + core profile out
def memory_inbox() -> Path:
    return ns() / "memory" / "observations" / "inbox"


def memory_done() -> Path:
    return ns() / "memory" / "observations" / "done"


def memory_facts() -> Path:
    return ns() / "memory" / "facts" / "current.ndjson"


def memory_core() -> Path:
    return ns() / "memory" / "core" / "current"


# scheduled tasks: rules the user wrote, firing at times the user chose.
# The scheduler drops due tasks into command/inbox as an ordinary command
# (writer "scheduler"), so they ride the same queue, tiers, and journal.
def schedule() -> Path:
    return ns() / "schedule" / "tasks.ndjson"


# Her channels (see namespace/README.md "Her"): the companion layer keeps its
# state beside the agent's, never inside it. her/intake, her/presence and
# her/devices are ordinary `current` docs resolved by state(); the two below
# are append-only logs with one writer each.
def her_unsent() -> Path:
    """What Her WOULD have said, and when — never delivered while the presence
    level is `quiet`. Shadow mode for speech (docs/proactivity.md)."""
    return ns() / "her" / "unsent.ndjson"


def her_pairing() -> Path:
    """The one live pairing code, if any (JSON doc, writer: her). Absent means
    no device may pair and the bridge has nothing to listen for."""
    return ns() / "her" / "pairing" / "current"
