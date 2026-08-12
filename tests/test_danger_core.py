# zero/tests/test_danger_core.py
#
# The executor is a seam, not a passthrough: these tests pin the behavior
# that keeps it honest — unknown tools rejected, mutations shadowed by
# default, confinement enforced, retries for reads only.

import os
import tempfile
import unittest
from pathlib import Path

from danger_core import policy
from danger_core.executor import DangerCore


class DangerCoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_root = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name
        self.root = Path(self._tmp.name).resolve()
        self.executor = DangerCore()

    def tearDown(self):
        if self._old_root is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old_root
        self._tmp.cleanup()

    def _set_mode(self, mode):
        mode_file = self.root / "namespace" / "control" / "mode"
        mode_file.parent.mkdir(parents=True, exist_ok=True)
        mode_file.write_text(mode)

    def test_unknown_tool_rejected(self):
        result = self.executor.execute_tool("perform_action", {"thought": "prose"})
        self.assertEqual(result["status"], "error")
        self.assertIn("unknown tool", result["message"])

    def test_missing_args_rejected_not_coerced(self):
        result = self.executor.execute_tool("read_file", {})
        self.assertEqual(result["status"], "error")
        self.assertIn("missing required args", result["message"])

    def test_default_mode_is_shadow(self):
        self.assertEqual(policy.current_mode(), policy.SHADOW)

    def test_garbage_mode_fails_closed_to_shadow(self):
        self._set_mode("yolo")
        self.assertEqual(policy.current_mode(), policy.SHADOW)

    def test_read_executes_even_in_shadow(self):
        target = self.root / "hello.txt"
        target.write_text("hi")
        result = self.executor.execute_tool("read_file", {"path": str(target)})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"]["content"], "hi")

    def test_write_shadowed_by_default(self):
        target = self.root / "f.txt"
        target.write_text("original")
        result = self.executor.execute_tool(
            "edit_file", {"path": str(target), "old_text": "original", "new_text": "changed"}
        )
        self.assertEqual(result["status"], "shadowed")
        self.assertEqual(target.read_text(), "original")  # nothing happened

    def test_write_executes_in_live_mode(self):
        self._set_mode("live")
        target = self.root / "f.txt"
        target.write_text("original")
        result = self.executor.execute_tool(
            "edit_file", {"path": str(target), "old_text": "original", "new_text": "changed"}
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(target.read_text(), "changed")

    def test_danger_never_auto_executes_even_live(self):
        self._set_mode("live")
        result = self.executor.execute_tool("run_command", {"cmd": ["echo", "hi"]})
        self.assertEqual(result["status"], "shadowed")

    def test_confinement_denied_outside_root(self):
        result = self.executor.execute_tool("read_file", {"path": "/etc/hosts"})
        self.assertEqual(result["status"], "error")
        self.assertIn("denied", result["message"])

    def test_control_channel_untouchable_even_live(self):
        self._set_mode("live")
        mode_file = self.root / "namespace" / "control" / "mode"
        result = self.executor.execute_tool(
            "write_file", {"path": str(mode_file), "content": "live"}
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("denied", result["message"])

    def test_retry_reads_only(self):
        self._set_mode("live")
        calls = {"read": 0, "write": 0}

        def flaky_read(**kwargs):
            calls["read"] += 1
            raise RuntimeError("flaky")

        def flaky_write(**kwargs):
            calls["write"] += 1
            raise RuntimeError("flaky")

        self.executor.registry["read_file"] = (flaky_read, policy.READ, ["path"], "")
        self.executor.registry["write_file"] = (flaky_write, policy.WRITE, ["path", "content"], "")

        r1 = self.executor.execute_tool("read_file", {"path": "x"})
        self.assertEqual(r1["status"], "error")
        self.assertEqual(calls["read"], 3)  # retried

        r2 = self.executor.execute_tool("write_file", {"path": "x", "content": "y"})
        self.assertEqual(r2["status"], "error")
        self.assertEqual(calls["write"], 1)  # never auto-retry a mutation


if __name__ == "__main__":
    unittest.main()
