# zero/memory.py
#
# Memory-v0: plain namespace files, ADD-only writes, read-time resolution.
# The brain proposes observations into a queue; the consolidator owns the
# facts file; the read path is keyword x recency x importance scoring —
# no embeddings until the scorer measurably misses (< ~10K facts).

import json
import math
import os
import re
import time
import uuid

from zero import ns, nspath

INJECT_BUDGET_CHARS = 6000  # ~1.5K tokens: load-bearing on gemma's context
RECENCY_HALF_LIFE_S = 7 * 86400


def submit_observation(text, subject="", importance=5, origin="", speaker=""):
    """Brain-side write path: queue one candidate fact (ADD-only).

    origin says where the words came from ("intake:name" = the user typed
    this in answer to a Her question; "" = the brain inferred it from a
    turn). speaker is who said it ("user", or "" when unknown) — the start
    of the attribution US-068 asks for. Both ride through to the fact line
    untouched, so a human reading facts.ndjson can tell told from guessed."""
    nspath.memory_inbox().mkdir(parents=True, exist_ok=True)
    doc = {
        "v": ns.SCHEMA_V, "ts": time.time(), "writer": "brain",
        "payload": {"text": text, "subject": subject, "importance": importance,
                    "origin": origin, "speaker": speaker},
    }
    ns._atomic(nspath.memory_inbox() / f"{time.time():.6f}-{uuid.uuid4().hex[:6]}.json",
               json.dumps(doc, ensure_ascii=False))


def drain_observations():
    """Consolidator-side: claim queued observations, append to facts.ndjson.
    Claim-by-rename, same contract as the command inbox."""
    nspath.memory_inbox().mkdir(parents=True, exist_ok=True)
    nspath.memory_done().mkdir(parents=True, exist_ok=True)
    appended = 0
    for p in sorted(nspath.memory_inbox().glob("*.json")):
        claimed = nspath.memory_done() / p.name
        try:
            os.replace(p, claimed)
        except FileNotFoundError:
            continue
        try:
            doc = json.loads(claimed.read_text())
            payload = doc.get("payload") or {}
            text = str(payload.get("text", "")).strip()
            if not text:
                continue
        except (json.JSONDecodeError, AttributeError):
            continue
        fact = {
            "id": uuid.uuid4().hex[:12],
            "text": text[:500],
            "subject": str(payload.get("subject", ""))[:80],
            "importance": min(10, max(1, int(payload.get("importance", 5)))),
            "ts_observed": doc.get("ts", time.time()),
            "ts_invalidated": None,
            "last_accessed": doc.get("ts", time.time()),
            "origin": str(payload.get("origin", ""))[:80],
            "speaker": str(payload.get("speaker", ""))[:40],
        }
        append_fact(fact)
        appended += 1
    return appended


def append_fact(fact):
    """Append one fact line. Owner: consolidator (single writer by contract)."""
    path = nspath.memory_facts()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(fact, ensure_ascii=False) + "\n")


def invalidate_fact(fact_id, now=None):
    """Stamp ts_invalidated on one fact — the only edit ever made to a fact
    line. Never a deletion: the record of what was once believed stays, so a
    contradiction is visible rather than silently rewritten. Returns True if
    a live fact with that id was stamped."""
    path = nspath.memory_facts()
    if not path.exists():
        return False
    now = time.time() if now is None else now
    out, hit = [], False
    for line in path.read_text().splitlines():
        try:
            fact = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue
        if fact.get("id") == fact_id and fact.get("ts_invalidated") is None:
            fact["ts_invalidated"] = now
            hit = True
        out.append(json.dumps(fact, ensure_ascii=False))
    if hit:
        ns._atomic(path, "\n".join(out) + "\n")
    return hit


def write_core(text):
    """Consolidator-side: replace the pinned profile block atomically. Empty
    text removes the block (no memory means no section)."""
    path = nspath.memory_core()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.strip():
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    ns._atomic(path, text.rstrip("\n"))


def load_facts(include_invalidated=False):
    path = nspath.memory_facts()
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            fact = json.loads(line)
        except json.JSONDecodeError:
            continue
        if include_invalidated or fact.get("ts_invalidated") is None:
            out.append(fact)
    return out


_WORD = re.compile(r"[a-z0-9]{3,}")


def _tokens(text):
    return set(_WORD.findall(str(text).lower()))


def score(fact, query_tokens, now=None):
    now = now or time.time()
    age = max(0.0, now - fact.get("last_accessed", fact.get("ts_observed", now)))
    recency = math.exp(-age / RECENCY_HALF_LIFE_S)
    overlap = len(_tokens(fact.get("text", "")) & query_tokens)
    return (1 + overlap) * fact.get("importance", 5) * (0.25 + recency)


def read_core():
    try:
        return nspath.memory_core().read_text().strip()
    except FileNotFoundError:
        return ""


def render(context, goal, budget_chars=INJECT_BUDGET_CHARS):
    """The read path: core block verbatim + top-K scored facts, under budget.
    Returns '' when there is nothing to say — no memory means no section."""
    parts = []
    core = read_core()
    if core:
        parts.append(core[: budget_chars // 2])
    facts = load_facts()
    if facts:
        q = _tokens(json.dumps(context)) | _tokens(goal)
        ranked = sorted(facts, key=lambda f: score(f, q), reverse=True)
        used = sum(len(p) for p in parts)
        lines = []
        for f in ranked:
            line = f"- {f['text']}"
            if used + len(line) > budget_chars:
                break
            lines.append(line)
            used += len(line) + 1
        if lines:
            parts.append("Known about the user:\n" + "\n".join(lines))
    return "\n\n".join(parts)
