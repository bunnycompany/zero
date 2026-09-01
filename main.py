# zero/main.py

import fcntl
import os
import sys
import time

from zero import consolidator, memory, ns, nspath, scheduler
from brain import answer
from her import intake as her_intake
from her import presence as her_presence
from danger_core.executor import DangerCore
from brain.remote import build_brain

IDLE_TICK_S = 10.0   # heartbeat cadence while idle
POLL_S = 0.5         # command-inbox poll interval
CONTEXT_STALE_S = 30.0

# Keeps the fd (and therefore the flock) alive for the process lifetime —
# a local variable would get garbage-collected, closing the fd and silently
# dropping the lock.
_lock_fd = None


def acquire_singleton_lock():
    """Exclusive, non-blocking lock so a launchd relaunch, a manual
    `./launch_zero.sh`, and `zero start` can never run two agent loops at
    once. brain.remote.build_brain() loads a multi-GB MLX model unconditionally
    in orchestrator.__init__; two instances is two model loads and an OOM on
    an 8GB Mac. Uses flock rather than a pidfile: the OS releases it the
    instant this process exits or is killed, clean shutdown or crash alike,
    so there is no stale-lock case to detect or clean up. Called first thing
    in run_agent_loop(), before anything else — including the model load."""
    global _lock_fd
    path = nspath.root() / ".zero.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        print(
            f"Zero is already running (lock held on {path}). "
            "Refusing to start a second instance — two copies loading the "
            "model at once would OOM.",
            file=sys.stderr,
        )
        sys.exit(1)
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    _lock_fd = fd


def set_status(status):
    ns.write_text("status", status, writer="main")


def say(brain, goal, call, result, memory=""):
    """Publish one plain-English answer for this turn. Always speaks."""
    if hasattr(brain, "_generate"):
        text = answer.compose(brain, goal, call, result, memory=memory)
    else:  # scripted brains in the wire tests
        text = answer.fallback(goal, call, result)
    ns.write_doc("answer", "main", {"text": text, "goal": goal})
    ns.log("main", "answered", text=text[:300])
    return text


def current_context():
    """Latest observer doc, or a fallback when the observer is silent/stale."""
    doc = ns.read_doc("context")
    if doc and time.time() - doc["ts"] < CONTEXT_STALE_S:
        return doc["payload"]
    return {"app": "unknown"}


def idle_heartbeat():
    """Fires once per idle tick (~every IDLE_TICK_S while nothing is
    happening). Refreshes the idle status and lets the consolidator drain
    memory/observations/inbox/ into memory/facts/current.ndjson — otherwise
    every fact the brain ever extracts sits queued forever and
    zero.memory.render() never sees any of it. No separate process: the
    whole loop is single-threaded, so this can never race a command turn."""
    set_status("idle")
    consolidator.run_once()
    # Her forms her presence on events only (a heartbeat, a turn, a context
    # change) and never generates: this is a file rewrite, not a model call.
    her_presence.tick()


def handle_commands(brain, executor):
    """One observe→think→act step, driven by the command inbox.

    Returns True if a command was handled. This is the whole agent step —
    the eval harness calls it directly with a scripted brain.
    """
    handled = False
    # Claim-and-process one command at a time (ns.iter_commands_full() is a
    # generator over the same claim-by-rename as take_commands_full(), but
    # take_commands_full()/list() would claim — i.e. rename inbox/ -> done/ —
    # every queued command up front, before any of them is executed. A crash
    # partway through the batch would then leave the rest sitting in done/,
    # indistinguishable from commands that were actually answered, and they
    # would never be retried. Claiming lazily here means a crash after
    # command K leaves K+1..N still in inbox/, so they get replayed on
    # restart. See failure-ledger.md #3.
    for c in ns.iter_commands_full():
        handled = True
        # Journal source with every ask: only "human" (organic) asks are
        # ground truth for the proactivity backtest; "scheduler" asks are not.
        ns.log("main", "command_received", text=c["text"], source=c.get("source", "human"),
               device=c.get("device", ""))

        # An answer to one of Her's questions is not a request: it is you
        # telling her about yourself. It never reaches decide() or a tool —
        # only commands that say reply_to are routed here, so Her can never
        # swallow a real ask by guessing.
        if her_intake.handles(c):
            set_status("thinking")
            text = her_intake.turn(c, brain)
            ns.write_doc("answer", "main", {"text": text, "goal": c["text"]})
            ns.log("main", "answered", text=text[:300], source=c.get("source", "human"), via="her")
            her_presence.refresh("intake")
            continue

        # FIFO, every message handled: messages that arrive while the model
        # is busy wait in the inbox and are processed in order — never dropped.
        goal = c["text"]
        set_status("thinking")
        context = current_context()
        remembered = memory.render(context, goal)
        try:
            call, raw, err = brain.decide(context, goal, executor.tool_manifest(), memory=remembered)
        except TypeError:  # scripted brains in the wire tests predate memory
            call, raw, err = brain.decide(context, goal, executor.tool_manifest())

        result = None
        if err == "gateway_unreachable":
            # The backend was down after retries. Speak an honest, actionable
            # line directly — don't route this through say()/compose(), which
            # would call the same dead gateway again just to phrase it.
            set_status("error")
            ns.write_doc("answer", "main",
                         {"text": "I can't reach the server right now — give it a moment and try again.",
                          "goal": c["text"]})
            ns.log("main", "answered", text="gateway unreachable", source=c.get("source", "human"))
            continue
        if call is None:
            ns.log("main", "decision_unparseable", error=err, raw=raw[:500])
        else:
            set_status("executing")
            result = executor.execute_tool(call["tool"], call["args"], source=c.get("source", "human"))
            ns.log("main", "tool_result", tool=call["tool"], result=result)
            if isinstance(result, dict):
                inner = result.get("result")
                if result.get("status") == "error" or (
                    isinstance(inner, dict) and inner.get("status") == "error"
                ):
                    set_status("error")  # the UI paints this red

        # Zero always says something back, in English — successes and
        # failures alike. Silence is what killed the previous prototype.
        say(brain, goal, call, result, memory=remembered)

        # hot write path: queue durable facts from this turn (ADD-only; the
        # consolidator owns everything downstream of the queue)
        if hasattr(brain, "extract_observations"):
            brain.extract_observations(goal, call, result)

        # the answer is what you see when you look; Her's line sits beside it
        her_presence.refresh("answered")

    if not handled:
        return False
    set_status("idle")
    return True


def run_agent_loop():
    acquire_singleton_lock()  # exits here if another instance already holds it
    ns.prune_done()
    ns.log("main", "startup")

    # say we are waking BEFORE the model loads: a local brain takes ~45s and
    # the UI would otherwise show a ready light for an agent that cannot answer
    set_status("waking")
    brain = build_brain()  # gateway when ZERO_API_KEY is set, else local MLX
    executor = DangerCore()

    set_status("idle")
    print("Zero is active. Waiting for commands...")

    last_beat = time.time()
    try:
        while True:
            # Scheduled tasks drop into the same inbox before we drain it, so a
            # due reminder is handled this very tick. This is the only thing
            # that puts a command there without a human — and it only ever
            # fires rules the human wrote.
            scheduler.tick()
            if handle_commands(brain, executor):
                last_beat = time.time()
                continue
            # Idle means idle: no goal, no unprompted generation. The only
            # thing that can wake the loop is a command — from you, or from a
            # schedule you set.
            if time.time() - last_beat >= IDLE_TICK_S:
                idle_heartbeat()
                last_beat = time.time()
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        set_status("idle")
        ns.log("main", "shutdown")
        print("Zero shutting down.")


if __name__ == "__main__":
    run_agent_loop()
