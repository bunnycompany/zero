# zero/ns.py
#
# The only module allowed to touch namespace/. Rules:
#   1. Exactly one writer per state channel (OWNERS, enforced).
#   2. All writes are atomic: temp file + fsync + os.replace.
#   3. State files carry a versioned JSON envelope; status stays plain text
#      so `cat` and `echo` keep working from a shell.
#   4. The namespace must live on a local APFS volume — os.replace atomicity
#      does not survive synced/network filesystems.

import json
import os
import tempfile
import time

from zero import nspath

SCHEMA_V = 1

# channel -> writer allowed to touch it. 'mode' has no entry on purpose:
# it is human-only (echo from a shell); code may read it, never write it.
OWNERS = {
    "status": "main",
    "context": "observer",
    "action": "brain",       # machine-readable: the tool call it chose
    "thinking": "brain",     # live reasoning tail while it works (ephemeral)
    "answer": "main",        # human-readable: what it says back, in English
    "checkpoint": "executor",
}


class OwnerViolation(RuntimeError):
    pass


def _channel_path(channel: str, writer: str):
    owner = OWNERS.get(channel)
    if owner is None:
        raise OwnerViolation(f"channel '{channel}' has no programmatic writer")
    if writer != owner:
        raise OwnerViolation(
            f"channel '{channel}' is owned by '{owner}', refusing write from '{writer}'"
        )
    return nspath.state(channel)


def _atomic(path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    # ".tmp-" prefix: a leading dot never matches "*", so half-written files
    # are invisible to any glob-based reader.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".swap")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def write_text(channel: str, text: str, writer: str):
    _atomic(_channel_path(channel, writer), text.rstrip("\n"))


def read_text(channel: str, default: str = "") -> str:
    try:
        return nspath.state(channel).read_text().strip()
    except FileNotFoundError:
        return default


def write_doc(channel: str, writer: str, payload):
    doc = {"v": SCHEMA_V, "ts": time.time(), "writer": writer, "payload": payload}
    _atomic(_channel_path(channel, writer), json.dumps(doc, ensure_ascii=False))


def read_doc(channel: str):
    """Returns the envelope dict, or None. Missing and malformed are both
    normal for 1Hz pollers; callers decide staleness via doc['ts']."""
    return _read_doc_file(nspath.state(channel))


def _read_doc_file(path):
    try:
        doc = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict) or doc.get("v") != SCHEMA_V:
        return None
    return doc


# --- command queue (UI/CLI -> agent) ---------------------------------------

def submit_command(text: str, source: str = "human"):
    """Drop one command file into the inbox. source distinguishes an organic
    ask ("human") from a scheduled one ("scheduler") — the proactivity
    backtest only counts organic asks as ground truth, so the two must never
    be conflated in the record."""
    nspath.inbox().mkdir(parents=True, exist_ok=True)
    now = time.time()
    doc = {"v": SCHEMA_V, "ts": now, "writer": source,
           "payload": {"text": text, "source": source}}
    _atomic(nspath.inbox() / f"{now:.6f}.json", json.dumps(doc, ensure_ascii=False))


def _claim_commands():
    """Claim-by-rename consumer: atomic, lock-free, oldest first. Yields the
    full payload dict. done/ doubles as an audit log of every command given."""
    nspath.inbox().mkdir(parents=True, exist_ok=True)
    nspath.done().mkdir(parents=True, exist_ok=True)
    for p in sorted(nspath.inbox().glob("*.json")):
        claimed = nspath.done() / p.name
        try:
            os.replace(p, claimed)  # a losing racer gets FileNotFoundError
        except FileNotFoundError:
            continue
        doc = _read_doc_file(claimed)
        if doc and isinstance(doc.get("payload"), dict) and "text" in doc["payload"]:
            payload = doc["payload"]
            payload.setdefault("source", doc.get("writer", "human"))
            yield payload


def take_commands():
    """Just the text, oldest first. The main loop's simple path."""
    return [c["text"] for c in _claim_commands()]


def take_commands_full():
    """Text plus source, for callers that must tell organic from scheduled.
    Claims (inbox/ -> done/) every currently-queued command up front, before
    returning. Fine for callers that consume the whole batch atomically as
    one unit; wrong for a caller that processes commands one at a time,
    since a crash mid-batch would then lose every command after the one in
    flight, not just that one. Use iter_commands_full() for that case."""
    return list(_claim_commands())


def iter_commands_full():
    """Text plus source, claimed and yielded one at a time, oldest first.
    Unlike take_commands_full(), nothing after the command a caller is
    currently handling has been claimed yet — so a crash mid-loop leaves
    the rest sitting in inbox/ to be replayed on restart, instead of sitting
    claimed-but-unprocessed in done/ forever. This is what the main loop
    uses; only call take_commands_full() when you truly want the batch."""
    return _claim_commands()


def prune_done(max_age_days: float = 7.0):
    """One file per command is an unbounded inode farm without this."""
    cutoff = time.time() - max_age_days * 86400
    done_dir = nspath.done()
    if not done_dir.exists():
        return
    for p in done_dir.glob("*.json"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except FileNotFoundError:
            pass


# --- journal ----------------------------------------------------------------

# Every turn appends several lines (brain/orchestrator.py alone logs up to
# 3000 chars of prompt per decision) with no other pruning in the module —
# left unchecked this file grows for the life of the install. Roll it by
# size instead: cheap (one stat() per append) and independent of how often
# the caller remembers to run startup maintenance.
JOURNAL_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
JOURNAL_BACKUPS = 3                   # journal.ndjson.1 .. .3, oldest dropped


def _rotate_journal_if_needed(journal):
    try:
        if journal.stat().st_size < JOURNAL_MAX_BYTES:
            return
    except FileNotFoundError:
        return
    oldest = journal.with_name(f"{journal.name}.{JOURNAL_BACKUPS}")
    try:
        oldest.unlink()
    except FileNotFoundError:
        pass
    for i in range(JOURNAL_BACKUPS - 1, 0, -1):
        src = journal.with_name(f"{journal.name}.{i}")
        if src.exists():
            os.replace(src, journal.with_name(f"{journal.name}.{i + 1}"))
    os.replace(journal, journal.with_name(f"{journal.name}.1"))


def log(writer: str, event: str, **fields):
    """Append one JSON line. Single write() call; append writes under
    PIPE_BUF are effectively atomic on macOS for lines this short."""
    journal = nspath.journal()
    journal.parent.mkdir(parents=True, exist_ok=True)
    _rotate_journal_if_needed(journal)
    line = json.dumps(
        {"ts": time.time(), "writer": writer, "event": event, **fields},
        ensure_ascii=False,
    )
    with open(journal, "a") as f:
        f.write(line + "\n")


def read_journal():
    """Yield journal entries oldest-first; the only sanctioned journal reader."""
    journal = nspath.journal()
    if not journal.exists():
        return
    with open(journal) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # torn tail line during concurrent append
