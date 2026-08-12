# zero/zero/scheduler.py
#
# Scheduling (adapted from Prime Agent's heartbeat idea): a rule the user
# wrote, firing at a time the user chose, becomes an ordinary command in the
# inbox — written by "scheduler" instead of "human". It reuses the whole
# existing spine: the queue, the tiers, shadow mode, the journal, the answer
# channel. No new execution path.
#
# This is proactivity with the judgment removed: all of the "it shows up on
# its own" value, none of the "it decided you needed it" risk. The only thing
# Zero decides is whether the clock says now.
#
# Tasks live in namespace/schedule/tasks.ndjson, one JSON object per line:
#   {"id", "text", "at": <unix>, "every": <seconds|null>, "created", "source"}
# A due task is dispatched into the inbox; a recurring one is rescheduled,
# a one-shot is marked done. The file has one writer: the scheduler.

import json
import time

from zero import ns, nspath


def _load():
    p = nspath.schedule()
    if not p.exists():
        return []
    tasks = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            tasks.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # a corrupt line must not stop the clock
    return tasks


def _save(tasks):
    p = nspath.schedule()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(t, ensure_ascii=False) for t in tasks)
    # atomic replace via ns's private helper keeps the one-writer contract
    ns._atomic(p, body)


def add(text, at, every=None):
    """Register a task. at=unix seconds; every=seconds for recurring."""
    tasks = _load()
    tasks.append({
        "id": f"{at:.0f}-{len(tasks)}",
        "text": text, "at": float(at), "every": every,
        "created": time.time(), "source": "scheduler", "done": False,
    })
    _save(tasks)
    ns.log("scheduler", "task_added", text=text, at=at, every=every)


def due(now=None):
    """Tasks whose time has come and are not yet done."""
    now = time.time() if now is None else now
    return [t for t in _load() if not t.get("done") and t.get("at", 0) <= now]


def tick(now=None):
    """Dispatch every due task into the command inbox, then reschedule or
    retire it. Returns how many fired. Safe to call every loop iteration."""
    now = time.time() if now is None else now
    tasks = _load()
    fired = 0
    changed = False
    for t in tasks:
        if t.get("done") or t.get("at", 0) > now:
            continue
        # a scheduled task is just a command someone else queued
        ns.submit_command(t["text"], source="scheduler")
        ns.log("scheduler", "fired", text=t["text"], id=t.get("id"))
        fired += 1
        changed = True
        if t.get("every"):
            # roll forward past now so a long sleep doesn't fire a storm
            nxt = t["at"] + t["every"]
            while nxt <= now:
                nxt += t["every"]
            t["at"] = nxt
        else:
            t["done"] = True
    if changed:
        _save(tasks)
    return fired
