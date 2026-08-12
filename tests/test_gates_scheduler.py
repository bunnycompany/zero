# zero/tests/test_gates_scheduler.py
#
# Gates: "done" must mean verified, not just returned.
# Scheduler: a task fires into the same inbox as a human ask, tagged source.

import os
import tempfile
import time
import unittest

from danger_core import gates
from danger_core.executor import DangerCore
from zero import ns, nspath, scheduler


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name
        # act for real so gates and writes actually run
        (nspath.state("mode")).parent.mkdir(parents=True, exist_ok=True)
        nspath.state("mode").write_text("live")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old
        self._tmp.cleanup()


class GateTests(SandboxCase):
    def test_write_then_verify_reads_it_back(self):
        ex = DangerCore()
        r = ex.execute_tool("write_file", {"path": "note.txt", "content": "hello"})
        self.assertEqual(r["status"], "success")
        self.assertIn("matches", r["verified"])

    def test_gate_catches_a_lie(self):
        # a tool that claims success but writes nothing must fail the gate
        ok, why = gates.verify("write_file", {"path": "ghost.txt", "content": "x"}, {"status": "success"})
        self.assertFalse(ok)
        self.assertIn("not there", why)

    def test_unknown_tool_passes_but_says_unverified(self):
        ok, why = gates.verify("read_file", {"path": "x"}, {"status": "success"})
        self.assertTrue(ok)
        self.assertIn("no gate", why)


class SchedulerTests(SandboxCase):
    def test_due_task_fires_into_inbox_as_scheduler(self):
        scheduler.add("water the plants", at=time.time() - 1)  # already due
        fired = scheduler.tick()
        self.assertEqual(fired, 1)
        cmds = ns.take_commands_full()
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0]["text"], "water the plants")
        self.assertEqual(cmds[0]["source"], "scheduler")  # NOT human — confound guard

    def test_future_task_does_not_fire(self):
        scheduler.add("later", at=time.time() + 3600)
        self.assertEqual(scheduler.tick(), 0)
        self.assertEqual(ns.take_commands(), [])

    def test_one_shot_retires_after_firing(self):
        scheduler.add("once", at=time.time() - 1)
        self.assertEqual(scheduler.tick(), 1)
        self.assertEqual(scheduler.tick(), 0)  # does not fire twice

    def test_recurring_reschedules_without_storm(self):
        # due 10 intervals ago, but a long sleep must fire once, not ten times
        scheduler.add("hourly", at=time.time() - 36000, every=3600)
        self.assertEqual(scheduler.tick(), 1)
        self.assertEqual(scheduler.tick(), 0)  # next one is in the future now

    def test_human_and_scheduler_asks_are_distinguishable(self):
        ns.submit_command("what's the weather", source="human")
        scheduler.add("daily standup", at=time.time() - 1)
        scheduler.tick()
        by_source = {c["source"] for c in ns.take_commands_full()}
        self.assertEqual(by_source, {"human", "scheduler"})


if __name__ == "__main__":
    unittest.main()


class RemoteCapTests(SandboxCase):
    # setUp writes mode=live, so these prove the cap overrides a live keyboard.
    def test_remote_write_is_capped_even_in_live(self):
        ex = DangerCore()
        r = ex.execute_tool("write_file", {"path": "x.txt", "content": "hi"}, source="remote")
        self.assertEqual(r["status"], "shadowed")  # NOT executed, though mode is live
        self.assertFalse((nspath.root() / "x.txt").exists())

    def test_local_write_still_executes_in_live(self):
        ex = DangerCore()
        r = ex.execute_tool("write_file", {"path": "y.txt", "content": "hi"}, source="human")
        self.assertEqual(r["status"], "success")

    def test_remote_read_is_allowed(self):
        (nspath.root() / "readme.txt").write_text("hello")
        ex = DangerCore()
        r = ex.execute_tool("read_file", {"path": "readme.txt"}, source="remote")
        self.assertEqual(r["status"], "success")  # reading from afar is fine

    def test_effective_mode_matrix(self):
        from danger_core import policy
        self.assertEqual(policy.effective_mode("live", "human"), "live")
        self.assertEqual(policy.effective_mode("live", "scheduler"), "live")
        self.assertEqual(policy.effective_mode("live", "remote"), "approve")
        self.assertEqual(policy.effective_mode("shadow", "remote"), "shadow")
