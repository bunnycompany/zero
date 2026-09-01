# zero/consolidator.py
#
# Sleep-time memory work, R1 scope: drain the observation queue into
# facts.ndjson while the agent is idle. Contradiction stamping, reflections,
# and the core-block rewrite are R2 — they land here when the gates pass.
#
#   ~/.venv/bin/python3 -m zero.consolidator          # one pass
#   ~/.venv/bin/python3 -m zero.consolidator --watch  # poll while idle

import sys
import time

from zero import memory, ns


def run_once():
    n = memory.drain_observations()
    if n:
        ns.log("consolidator", "facts_appended", count=n)
        refresh_core()
    return n


def refresh_core():
    """Re-render the pinned profile block from what the user actually said
    (her/profile.py). Only runs when facts changed; writes only when the
    text changed, so an idle agent never rewrites the file."""
    from her import profile
    text = profile.render()
    if text != memory.read_core():
        memory.write_core(text)
        ns.log("consolidator", "core_rewritten", chars=len(text))


def watch(poll_s=30.0):
    while True:
        if ns.read_text("status", default="idle") == "idle":
            run_once()
        time.sleep(poll_s)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        print(f"appended {run_once()} fact(s)")
