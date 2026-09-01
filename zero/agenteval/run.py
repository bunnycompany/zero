# zero/agenteval/run.py
#
# Layer-2 agent eval: the real model driving the real agent step in a
# sandbox namespace per scenario. Run:
#
#   ZERO_RUN_MODEL_EVAL=1 python -m zero.agenteval.run
#
# Every run records model, scorer version, and code sha — two runs are
# comparable only if both match (the old eval's unreproducible-passes
# lesson, encoded).

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCORER_VERSION = 1


def _code_sha(repo_root):
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        sha = out.stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() != ""
        return sha, dirty
    except Exception:
        return "unknown", True


def run_all():
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))

    from zero.agenteval.scenarios import SCENARIOS

    # Import order matters: main/brain/executor resolve ZERO_ROOT at call
    # time, so the sandbox env set per-scenario below is what they see.
    from brain.remote import build_brain
    from danger_core.executor import DangerCore
    import main as agent_main
    from zero import memory, ns, nspath

    print("Building brain (gateway if ZERO_API_KEY is set, else local MLX)...")
    brain = build_brain()

    results = []
    old_root = os.environ.get("ZERO_ROOT")
    for sc in SCENARIOS:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ZERO_ROOT"] = tmp
            root = Path(tmp).resolve()
            for rel, content in sc["seed"].items():
                (root / rel).write_text(content)

            # memory scenarios seed pre-consolidated facts (as the
            # consolidator would have written them)
            now = time.time()
            for mf in sc.get("memory_facts", []):
                memory.append_fact({
                    "id": f"seed-{mf['subject']}-{mf.get('invalidated', False)}",
                    "text": mf["text"], "subject": mf.get("subject", ""),
                    "importance": mf.get("importance", 5), "ts_observed": now,
                    "ts_invalidated": now if mf.get("invalidated") else None,
                    "last_accessed": now,
                    "origin": mf.get("origin", ""), "speaker": mf.get("speaker", ""),
                })

            executor = DangerCore()
            ns.submit_command(sc["command"])
            t0 = time.time()
            error = None
            try:
                agent_main.handle_commands(brain, executor)
            except Exception as e:  # a crash is a scenario failure, not a harness failure
                error = f"{type(e).__name__}: {e}"
            latency = time.time() - t0

            journal = nspath.journal()
            events = []
            if journal.exists():
                events = [json.loads(l) for l in journal.read_text().strip().split("\n")]

            # A brain that produced nothing makes every abstention scenario
            # "pass" vacuously — this is how an eval starts reporting
            # meaningless numbers. A silent brain is a harness error, never a
            # score. (Caught live: a 503 gateway "scored" 7/9.)
            brain_spoke = any(
                e.get("event") in ("proposed", "executed") or
                (e.get("event") == "decision_unparseable" and (e.get("raw") or "").strip())
                for e in events
            )
            if error:
                passed, detail = False, error
            elif not brain_spoke:
                passed, detail = False, "BRAIN SILENT — no output at all (dead model/gateway?)"
            else:
                passed, detail = sc["check"](events, root)
            status_ok = ns.read_text("status", default="idle") == "idle"
            if not status_ok:
                passed, detail = False, f"{detail}; status stuck: {ns.read_text('status')}"

            results.append({
                "id": sc["id"], "passed": passed, "detail": detail,
                "latency_s": round(latency, 1),
            })
            print(f"  {'PASS' if passed else 'FAIL'}  {sc['id']:38s} {latency:5.1f}s  {detail}")

    if old_root is None:
        os.environ.pop("ZERO_ROOT", None)
    else:
        os.environ["ZERO_ROOT"] = old_root

    sha, dirty = _code_sha(repo_root)
    record = {
        "schema_version": 1,
        "ts": time.time(),
        "model": brain.model_path,
        "scorer_version": SCORER_VERSION,
        "code_sha": sha,
        "dirty": dirty,
        "layer": "model",  # wiring layer is tests/test_agent_wire.py
        "results": results,
    }
    runs_dir = repo_root / "eval_results" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out = runs_dir / f"{time.strftime('%Y%m%d_%H%M%S')}__{sha}{'~' if dirty else ''}.json"
    out.write_text(json.dumps(record, indent=2))

    n_pass = sum(r["passed"] for r in results)
    print(f"\nmodel layer: {n_pass}/{len(results)} passed  ({brain.model_path}, scorer v{SCORER_VERSION}, {sha}{'+dirty' if dirty else ''})")
    print(f"record: {out}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    if not os.environ.get("ZERO_RUN_MODEL_EVAL"):
        print("Loads the full MLX model. Set ZERO_RUN_MODEL_EVAL=1 to confirm.")
        sys.exit(2)
    sys.exit(run_all())
