# zero/tests/test_policy_confinement.py
#
# The agent must not be able to change what it is allowed to do next, or
# rewrite the record of what it did. Audit finding, 2026-07-30.

import os
import tempfile
import unittest
from pathlib import Path

from danger_core import policy


class ConfinementTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name
        # a fake owner home, separate from the root, with the real folders in it
        self._home = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = self._home.name
        self.home = Path(self._home.name).resolve()
        for name in ("Downloads", "Desktop", "Documents", ".ssh"):
            (self.home / name).mkdir()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        self._tmp.cleanup()
        self._home.cleanup()

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

    # --- US-024: reads may look at the owner's real folders ----------------

    def test_readable_allows_owner_folders(self):
        (self.home / "Downloads" / "invoice.pdf").write_text("x")
        for path in ("~/Downloads", "~/Downloads/invoice.pdf", "~/Desktop",
                     "~/Documents/notes.txt", str(self.home / "Documents")):
            p = policy.resolve_readable(path)
            self.assertTrue(p.is_relative_to(self.home), path)

    def test_readable_keeps_root_and_denied_surfaces(self):
        root = policy.allowed_root()
        self.assertTrue(policy.resolve_readable("notes.txt").is_relative_to(root))
        for path in ("namespace/control/mode", "danger_core/policy.py", "launch_zero.sh"):
            with self.assertRaises(PermissionError, msg=f"{path} must stay denied"):
                policy.resolve_readable(path)

    def test_readable_refuses_escape_from_owner_folders(self):
        for path in ("~/Downloads/../.ssh/id_rsa", "~/Downloads/../../etc/passwd",
                     "~/.ssh/id_rsa", "~", "/etc/hosts", "~/Downloads2"):
            with self.assertRaises(PermissionError, msg=f"{path} must be denied"):
                policy.resolve_readable(path)

    def test_readable_refuses_symlink_that_leaves_downloads(self):
        link = self.home / "Downloads" / "sneaky"
        link.symlink_to("/etc")
        with self.assertRaises(PermissionError):
            policy.resolve_readable(str(link / "hosts"))

    def test_writes_stay_confined_to_root(self):
        # widening was for reads only: the write resolver must not follow
        for path in ("~/Downloads/invoice.pdf", "~/Desktop/x.txt", "~/Documents"):
            with self.assertRaises(PermissionError, msg=f"{path} must be write-denied"):
                policy.resolve_confined(path)

    def test_readable_roots_follow_home_at_call_time(self):
        before = policy.readable_roots()
        with tempfile.TemporaryDirectory() as other:
            os.environ["HOME"] = other
            after = policy.readable_roots()
        self.assertNotEqual(before, after)
        self.assertTrue(all(r.is_relative_to(Path(other).resolve()) for r in after))


if __name__ == "__main__":
    unittest.main()
