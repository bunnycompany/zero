# zero/tests/test_policy_confinement.py
#
# The agent must not be able to change what it is allowed to do next, or
# rewrite the record of what it did. Audit finding, 2026-07-30.

import os
import tempfile
import unittest

from danger_core import policy


class ConfinementTestCase(unittest.TestCase):
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

    def test_denies_self_modification_surfaces(self):
        for path in ("launch_zero.sh", "main.py", "zero/nspath.py", "zero/ns.py",
                     "brain/orchestrator.py", "danger_core/policy.py",
                     "namespace/control/mode", "namespace/log/journal.ndjson",
                     "namespace/command/inbox/x.json"):
            with self.assertRaises(PermissionError, msg=f"{path} must be denied"):
                policy.resolve_confined(path)

    def test_denies_escape_via_traversal(self):
        for path in ("../../etc/passwd", "~/.ssh/id_rsa", "/etc/hosts"):
            with self.assertRaises(PermissionError):
                policy.resolve_confined(path)

    def test_allows_ordinary_work_paths(self):
        root = policy.allowed_root()  # resolved (/var -> /private/var on macOS)
        for path in ("notes.txt", "projects/todo.md", "namespace/memory/facts/current.ndjson"):
            self.assertTrue(policy.resolve_confined(path).is_relative_to(root))


if __name__ == "__main__":
    unittest.main()
