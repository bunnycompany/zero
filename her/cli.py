# her/cli.py — the `her` command. A thin reader of the namespace plus the
# few writes a human makes by hand (open a pairing, review the unsent log,
# strike a fact). It never runs a brain and never touches control/.
#
#   her                      what she'd say if you looked — and her question, if any
#   her <words>              answer her question, or ask Zero through her
#   her skip                 pass on the current question
#   her profile              everything she knows, in your words, with ids
#   her forget <fact-id>     strike a fact out (kept, stamped, never used again)
#   her pair                 show a code for your phone
#   her glasses              mint a link for your Ray-Ban Display (shown once)
#   her devices | her forget-device <id>
#   her unsent | her review  what she would have said; tell her if you'd have wanted it
#   her level                where the speech ladder is, and how a human moves it
#   her status

import json
import os
import sys
import time

from her import devices, intake, presence, profile
from zero import memory, ns, nspath

PORT = devices.BRIDGE_PORT


def _alive():
    try:
        return time.time() - nspath.state("status").stat().st_mtime < 30
    except FileNotFoundError:
        return False


def _answer_text():
    doc = ns.read_doc("answer")
    return (doc or {}).get("payload", {}).get("text", "")


def _her_name():
    for f in memory.load_facts():
        if f.get("origin") == "intake:her_name":
            return f["text"].replace("Calls their assistant", "").strip()
    return "Her"


def cmd_show():
    p = presence.current()
    name = _her_name()
    if not _alive():
        print(f"  {name} isn't awake — start Zero with  zero start  and she comes with it.")
    if p:
        print(f"  {name} › {p['line']}")
    else:
        print(f"  {name} › Hello. I don't know you yet — that's the point of the next few days.")
    q = intake.pending() if not p else (intake.question(p["question"]["id"]) if p.get("question") else None)
    if q:
        print(f"\n  she asks › {q['ask']}")
        print("             (answer with  her <your answer>   or   her skip)")
    last = _answer_text()
    if last:
        print(f"\n  zero › {last}")
    return 0


def _wait_for_answer(before_ts, timeout=90):
    sys.stdout.write("  thinking")
    sys.stdout.flush()
    for _ in range(timeout):
        doc = ns.read_doc("answer")
        if doc and doc.get("ts", 0) > before_ts:
            print(f"\n  {_her_name()} › {doc['payload'].get('text', '')}")
            return 0
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1)
    print("\n  (still working — check back with:  her)")
    return 0


def cmd_say(words, skip=False):
    text = "skip" if skip else " ".join(words).strip()
    q = intake.pending()
    doc = ns.read_doc("answer")
    before = doc.get("ts", 0) if doc else 0
    if q:
        ns.submit_command(text, source="human", reply_to=q["id"])
    elif skip:
        print("  Nothing to skip — she hasn't asked anything.")
        return 0
    else:
        ns.submit_command(text, source="human")
    if not _alive():
        print("  Zero isn't running, so this will be waiting for her when she wakes:  zero start")
        return 0
    return _wait_for_answer(before)


def cmd_profile():
    facts = profile.facts_for_display()
    if not facts:
        print("  She knows nothing about you yet. Say  her  to see her first question.")
        return 0
    print("  What she knows — your words are marked ‘you said’; the rest she inferred:\n")
    for f in facts:
        src = "you said" if str(f.get("origin", "")).startswith("intake:") else "inferred"
        when = time.strftime("%-d %b", time.localtime(f.get("ts_observed", 0)))
        print(f"  {f['id']}  {f['text']}   ({src}, {when})")
    print("\n  Strike one out with  her forget <id>  — it stays on file, crossed out, never used.")
    return 0


def cmd_forget(fid):
    if memory.invalidate_fact(fid):
        from zero import consolidator
        consolidator.refresh_core()
        print("  Crossed out. She won't use that again.")
        return 0
    print("  No live fact with that id.")
    return 1


def cmd_pair():
    code = devices.open_pairing()
    ip = devices.lan_ip()
    print(f"\n  On your phone, open Her → Pair, and enter:\n")
    print(f"      address   http://{ip}:{PORT}")
    print(f"      code      {code}\n")
    print("  The code works once and dies in ten minutes. Waiting…")
    known = set(devices.list_devices())
    for _ in range(devices.PAIR_TTL_S):
        now = set(devices.list_devices())
        new = now - known
        if new:
            did = new.pop()
            d = devices.list_devices()[did]
            print(f"\n  Paired: {d['name']} ({d['kind']}). It can ask her anything; it can never change this Mac.")
            return 0
        if devices.pairing() is None:
            print("\n  That code is gone (used, expired, or too many wrong tries). Run  her pair  again.")
            return 1
        time.sleep(1)
    print("\n  Nothing paired in ten minutes. Run  her pair  again when you're ready.")
    return 1


def cmd_glasses():
    code = devices.open_pairing()
    did, token = devices.pair(code, "Ray-Ban Meta Display", "glasses")
    ip = devices.lan_ip()
    print("\n  Your glasses' link — shown once, never stored here:\n")
    print(f"      http://{ip}:{PORT}/glasses/?t={token}\n")
    print("  In the Meta AI app, turn on Developer Mode and add that URL as a web app.")
    print("  It only works on your own wifi. Revoke it any time:  her forget-device", did)
    return 0


def cmd_devices():
    reg = devices.list_devices()
    if not reg:
        print("  No devices paired. She lives on this Mac only.  her pair  adds your phone.")
        return 0
    for did, d in reg.items():
        seen = time.strftime("%-d %b %H:%M", time.localtime(d.get("last_seen", 0)))
        print(f"  {did}  {d['name']} ({d['kind']})  last heard {seen}")
    return 0


def cmd_forget_device(did):
    if devices.forget(did):
        print("  Forgotten. Whatever that device sends from now on is ignored.")
        return 0
    print("  No device with that id.")
    return 1


def cmd_unsent():
    items = presence.unreviewed()
    if not items:
        print("  Nothing waiting. She hasn't formed an opinion she'd have spoken.")
        return 0
    print("  What she would have said, and didn't:\n")
    for e in items:
        when = time.strftime("%-d %b %H:%M", time.localtime(e.get("ts", 0)))
        print(f"  {e['id']}  {when}  {e['text']}   [{e.get('trigger')}]")
    print("\n  Tell her whether you'd have wanted each one:  her review")
    return 0


def cmd_review():
    items = presence.unreviewed()
    if not items:
        print("  Nothing to review.")
        return 0
    if not sys.stdin.isatty():
        print("  Review needs a terminal (it asks y/n per line).")
        return 1
    for e in items:
        ans = input(f"\n  “{e['text']}”\n  Would you have wanted her to say this? [y/n/q] ").strip().lower()
        if ans == "q":
            break
        presence.review(e["id"], wanted=(ans == "y"))
    n, p = presence.precision()
    print(f"\n  {n} reviewed, {p:.0%} wanted. Live speech needs {presence.LIVE_MIN_REVIEWED} reviewed at ≥{presence.LIVE_MIN_PRECISION:.0%}.")
    return 0


def cmd_level():
    lv, dl = presence.level(), presence.delivery_level()
    n, p = presence.precision()
    print(f"  presence level: {lv}" + (f" (delivering as {dl} — no precision record yet)" if lv != dl else ""))
    print(f"  reviewed: {n}, wanted: {p:.0%}")
    print("\n  Only a human moves this, by hand — she cannot:")
    print("      echo quiet   > namespace/control/presence    she writes, never speaks (default)")
    print("      echo digest  > namespace/control/presence    at most one line a day, when you look")
    print("      echo ambient > namespace/control/presence    a dot / a glyph when something's there")
    print("      echo live    > namespace/control/presence    a notification — only with a good review record")
    return 0


def cmd_status():
    answered, total = intake.progress()
    print(f"  {'awake' if _alive() else 'asleep'} · presence {presence.level()} · "
          f"{answered}/{total} questions answered · {len(devices.list_devices())} device(s)")
    print(f"  {intake.summary()}")
    return 0


HELP = """
  her — the part of Zero that gets to know you.

    her                      what she'd say if you looked — and her question, if any
    her <words>              answer her question, or ask Zero through her
    her skip                 pass on the current question
    her profile              everything she knows, in your words, with ids
    her forget <fact-id>     strike a fact out (kept, stamped, never used again)
    her pair                 show a code for your phone
    her glasses              mint a link for your Ray-Ban Display (shown once)
    her devices              what's paired      her forget-device <id>   revoke one
    her unsent               what she would have said, and didn't
    her review               tell her, line by line, if you'd have wanted it
    her level                where the speech ladder is, and how a human moves it
    her status

  She asks at most three questions a day, keeps your answers word for word,
  and never speaks first unless a human raises her level by hand.
"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return cmd_show()
    c, rest = argv[0], argv[1:]
    table = {
        "help": lambda: (print(HELP), 0)[1],
        "--help": lambda: (print(HELP), 0)[1],
        "-h": lambda: (print(HELP), 0)[1],
        "skip": lambda: cmd_say([], skip=True),
        "profile": cmd_profile,
        "pair": cmd_pair,
        "glasses": cmd_glasses,
        "devices": cmd_devices,
        "unsent": cmd_unsent,
        "review": cmd_review,
        "level": cmd_level,
        "status": cmd_status,
    }
    if c in table:
        return table[c]()
    if c == "forget" and rest:
        return cmd_forget(rest[0])
    if c == "forget-device" and rest:
        return cmd_forget_device(rest[0])
    return cmd_say(argv)


if __name__ == "__main__":
    sys.exit(main())
