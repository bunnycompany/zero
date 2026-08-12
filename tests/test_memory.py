# zero/tests/test_memory.py
#
# Memory-v0 contract: queue -> drain -> facts -> scored render, all in a
# ZERO_ROOT sandbox, no MLX.

import os
import tempfile
import time
import unittest

from zero import memory, ns, nspath


class MemoryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old
        self._tmp.cleanup()

    def test_queue_drain_roundtrip(self):
        memory.submit_observation("prefers the ~/.venv python", "python", 8)
        memory.submit_observation("works at a cafe on Wednesdays", "schedule", 4)
        self.assertEqual(memory.drain_observations(), 2)
        self.assertEqual(memory.drain_observations(), 0)  # queue empty now
        facts = memory.load_facts()
        self.assertEqual(len(facts), 2)
        self.assertTrue(all(f["ts_invalidated"] is None for f in facts))

    def test_invalidated_facts_excluded(self):
        memory.append_fact({"id": "a", "text": "old", "subject": "x",
                            "importance": 5, "ts_observed": time.time(),
                            "ts_invalidated": time.time(), "last_accessed": time.time()})
        memory.append_fact({"id": "b", "text": "new", "subject": "x",
                            "importance": 5, "ts_observed": time.time(),
                            "ts_invalidated": None, "last_accessed": time.time()})
        self.assertEqual([f["id"] for f in memory.load_facts()], ["b"])
        self.assertEqual(len(memory.load_facts(include_invalidated=True)), 2)

    def test_render_relevance_and_budget(self):
        memory.append_fact({"id": "1", "text": "user runs tests with the venv python",
                            "subject": "python", "importance": 9,
                            "ts_observed": time.time(), "ts_invalidated": None,
                            "last_accessed": time.time()})
        memory.append_fact({"id": "2", "text": "likes oat milk", "subject": "coffee",
                            "importance": 2, "ts_observed": time.time(),
                            "ts_invalidated": None, "last_accessed": time.time()})
        out = memory.render({"app": "Terminal"}, "please run the tests")
        self.assertIn("venv python", out)
        self.assertLessEqual(len(out), memory.INJECT_BUDGET_CHARS)
        # relevant fact must outrank the irrelevant one
        self.assertLess(out.find("venv"), out.find("oat") % (len(out) + 1) if "oat" in out else len(out))

    def test_render_empty_when_no_memory(self):
        self.assertEqual(memory.render({"app": "unknown"}, "anything"), "")

    def test_core_block_injected_first(self):
        nspath.memory_core().parent.mkdir(parents=True, exist_ok=True)
        nspath.memory_core().write_text("The user is Dal, a Daylight consultant.")
        out = memory.render({"app": "unknown"}, "hello")
        self.assertTrue(out.startswith("The user is Dal"))

    def test_malformed_queue_files_skipped(self):
        nspath.memory_inbox().mkdir(parents=True, exist_ok=True)
        (nspath.memory_inbox() / "junk.json").write_text("{not json")
        self.assertEqual(memory.drain_observations(), 0)

    def test_journal_reader(self):
        ns.log("main", "startup")
        ns.log("brain", "decision_prompt", prompt="p", goal="g")
        events = list(ns.read_journal())
        self.assertEqual([e["event"] for e in events], ["startup", "decision_prompt"])


if __name__ == "__main__":
    unittest.main()
