# zero/tests/test_ns.py
#
# Contract tests for the namespace. Runs entirely in a tmpdir sandbox via
# ZERO_ROOT — never touches the live namespace, never loads MLX.

import json
import os
import tempfile
import unittest

from zero import ns, nspath


class NamespaceTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_root = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name

    def tearDown(self):
        if self._old_root is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old_root
        self._tmp.cleanup()

    def test_root_resolves_to_sandbox(self):
        from pathlib import Path
        self.assertEqual(nspath.root(), Path(self._tmp.name).resolve())
        self.assertEqual(nspath.ns(), nspath.root() / "namespace")

    def test_text_roundtrip_strips_trailing_newline(self):
        ns.write_text("status", "thinking\n", writer="main")
        self.assertEqual(ns.read_text("status"), "thinking")
        raw = nspath.state("status").read_text()
        self.assertEqual(raw, "thinking")  # no trailing newline on disk

    def test_read_text_default_when_missing(self):
        self.assertEqual(ns.read_text("status", default="idle"), "idle")

    def test_owner_enforcement(self):
        with self.assertRaises(ns.OwnerViolation):
            ns.write_text("status", "idle", writer="brain")
        with self.assertRaises(ns.OwnerViolation):
            ns.write_doc("action", "main", {"text": "nope"})

    def test_mode_is_human_only(self):
        for writer in ("main", "brain", "executor", "observer"):
            with self.assertRaises(ns.OwnerViolation):
                ns.write_text("mode", "live", writer=writer)
        # but code may read what a human echoed there
        nspath.state("mode").parent.mkdir(parents=True, exist_ok=True)
        nspath.state("mode").write_text("shadow\n")
        self.assertEqual(ns.read_text("mode"), "shadow")

    def test_doc_roundtrip_envelope(self):
        ns.write_doc("action", "brain", {"text": "hello", "model": "m"})
        doc = ns.read_doc("action")
        self.assertEqual(doc["v"], ns.SCHEMA_V)
        self.assertEqual(doc["writer"], "brain")
        self.assertEqual(doc["payload"]["text"], "hello")
        self.assertIsInstance(doc["ts"], float)

    def test_read_doc_none_on_malformed(self):
        path = nspath.state("context")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json at all")
        self.assertIsNone(ns.read_doc("context"))
        path.write_text(json.dumps({"v": 999, "payload": {}}))
        self.assertIsNone(ns.read_doc("context"))

    def test_command_queue_claim_semantics(self):
        ns.submit_command("first")
        ns.submit_command("second")
        got = ns.take_commands()
        self.assertEqual(got, ["first", "second"])  # oldest first
        self.assertEqual(ns.take_commands(), [])  # already claimed
        # consumed commands are preserved in done/ as an audit trail
        self.assertEqual(len(list(nspath.done().glob("*.json"))), 2)

    def test_inflight_tmp_files_invisible_to_queue(self):
        nspath.inbox().mkdir(parents=True, exist_ok=True)
        (nspath.inbox() / ".tmp-halfwritten.json").write_text("{")
        self.assertEqual(ns.take_commands(), [])

    def test_journal_appends_lines(self):
        ns.log("main", "startup")
        ns.log("executor", "proposed", tool="read_file")
        lines = nspath.journal().read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)
        first, second = (json.loads(l) for l in lines)
        self.assertEqual(first["event"], "startup")
        self.assertEqual(second["tool"], "read_file")

    def test_journal_rotates_past_size_cap(self):
        # Shrink the cap so the test doesn't need to write 10MB for real.
        old_max = ns.JOURNAL_MAX_BYTES
        ns.JOURNAL_MAX_BYTES = 200
        try:
            for i in range(30):
                ns.log("main", "tick", n=i, pad="x" * 20)
            journal = nspath.journal()
            self.assertTrue(journal.exists())
            self.assertTrue(journal.stat().st_size < ns.JOURNAL_MAX_BYTES * 2)
            self.assertTrue((journal.parent / "journal.ndjson.1").exists())
            # rotation never loses the most recent event
            last = list(ns.read_journal())[-1]
            self.assertEqual(last["n"], 29)
        finally:
            ns.JOURNAL_MAX_BYTES = old_max

    def test_journal_rotation_caps_backup_count(self):
        old_max = ns.JOURNAL_MAX_BYTES
        ns.JOURNAL_MAX_BYTES = 50
        try:
            for i in range(200):
                ns.log("main", "tick", n=i, pad="x" * 20)
            journal = nspath.journal()
            siblings = sorted(p.name for p in journal.parent.glob("journal.ndjson*"))
            # current file + at most JOURNAL_BACKUPS rotated files — never
            # an ever-growing pile of .4, .5, .6...
            self.assertLessEqual(len(siblings), 1 + ns.JOURNAL_BACKUPS)
            self.assertNotIn(f"journal.ndjson.{ns.JOURNAL_BACKUPS + 1}", siblings)
        finally:
            ns.JOURNAL_MAX_BYTES = old_max

    def test_atomic_write_leaves_no_debris(self):
        for i in range(20):
            ns.write_text("status", f"tick-{i}", writer="main")
        leftovers = [p for p in nspath.state("status").parent.iterdir() if p.name != "current"]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
