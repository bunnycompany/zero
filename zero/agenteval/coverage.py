# zero/agenteval/coverage.py
#
# The loop-closing instrument: every promise we make to a user should map to a
# scenario that can fail. This reports which promises are covered by a check,
# which are asserted only by prose, and which scenarios exist without a promise
# behind them (usually fine — safety checks — but worth seeing).
#
#   python -m zero.agenteval.coverage

PROMISES = {
    # id -> the promise as a user would hear it, from docs/north-star.html
    "answers_every_turn":  "It always answers, in one plain sentence.",
    "says_when_it_fails":  "When something fails it says so, and what to try next.",
    "never_shows_jargon":  "It never shows tool calls or internal names.",
    "shadow_is_explained": "In shadow mode it tells you what it would have done.",
    "refuses_destruction": "It won't destroy your files when asked carelessly.",
    "remembers_you":       "It remembers what you tell it and uses it later.",
    "forgets_stale_facts": "When something changes, the old version stops being used.",
    "admits_not_knowing":  "If it doesn't know, it says so instead of guessing.",
    "survives_odd_input":  "Strange or hostile input doesn't break it.",
}


def report():
    from zero.agenteval.scenarios import SCENARIOS

    covered = {}
    orphans = []
    for sc in SCENARIOS:
        pid = sc.get("proves")
        if pid:
            covered.setdefault(pid, []).append(sc["id"])
        else:
            orphans.append(sc["id"])

    print("PROMISE COVERAGE\n")
    uncovered = []
    for pid, text in PROMISES.items():
        scenarios = covered.get(pid)
        if scenarios:
            print(f"  ✓ {text}")
            for s in scenarios:
                print(f"      proved by {s}")
        else:
            uncovered.append(pid)
            print(f"  ✗ {text}")
            print("      NO CHECK — this promise is prose only")
    unknown = [p for p in covered if p not in PROMISES]
    if unknown:
        print(f"\n  scenarios claim unknown promises: {unknown}")
    if orphans:
        print(f"\n  scenarios with no promise attached: {', '.join(orphans)}")

    print(f"\n{len(PROMISES) - len(uncovered)}/{len(PROMISES)} promises have a check that can fail.")
    return 0 if not uncovered else 1


if __name__ == "__main__":
    raise SystemExit(report())
