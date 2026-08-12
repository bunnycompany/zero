# zero/tests/test_tools.py
#
# The sed replacement: literal semantics, count guard, snapshots, timeouts.

import os
import tempfile
import unittest
from pathlib import Path

from danger_core.tools import ToolDispatcher


class ToolsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_root = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name
        self.root = Path(self._tmp.name).resolve()
        self.tools = ToolDispatcher()

    def tearDown(self):
        if self._old_root is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old_root
        self._tmp.cleanup()

    def _mk(self, name, content):
        p = self.root / name
        p.write_text(content)
        return p

    def test_edit_is_literal_not_regex(self):
        # under sed, "a.c" also matched "abc" and "aXc" — never again
        p = self._mk("f.txt", "a.c abc aXc\n")
        result = self.tools.edit_file(str(p), "a.c", "HIT")
        self.assertEqual(result["status"], "success")
        self.assertEqual(p.read_text(), "HIT abc aXc\n")

    def test_pipe_and_ampersand_are_inert(self):
        # "|" broke the sed expression; "&" expanded to the whole match
        p = self._mk("f.txt", "value\n")
        result = self.tools.edit_file(str(p), "value", "a|b&c")
        self.assertEqual(result["status"], "success")
        self.assertEqual(p.read_text(), "a|b&c\n")

    def test_multiline_edits_work(self):
        p = self._mk("f.txt", "line1\nline2\nline3\n")
        result = self.tools.edit_file(str(p), "line1\nline2", "merged")
        self.assertEqual(result["status"], "success")
        self.assertEqual(p.read_text(), "merged\nline3\n")

    def test_expect_guard_zero_occurrences(self):
        p = self._mk("f.txt", "hello\n")
        result = self.tools.edit_file(str(p), "absent", "x")
        self.assertEqual(result["status"], "error")
        self.assertIn("found 0", result["message"])
        self.assertEqual(p.read_text(), "hello\n")

    def test_expect_guard_multiple_occurrences(self):
        # the old sed /g silently replaced every occurrence in the file
        p = self._mk("f.txt", "dup dup dup\n")
        result = self.tools.edit_file(str(p), "dup", "x")
        self.assertEqual(result["status"], "error")
        self.assertIn("found 3", result["message"])
        self.assertEqual(p.read_text(), "dup dup dup\n")

    def test_explicit_expect_allows_bulk_replace(self):
        p = self._mk("f.txt", "dup dup dup\n")
        result = self.tools.edit_file(str(p), "dup", "x", expect=3)
        self.assertEqual(result["status"], "success")
        self.assertEqual(p.read_text(), "x x x\n")

    def test_backup_snapshot_taken_before_edit(self):
        p = self._mk("f.txt", "before\n")
        result = self.tools.edit_file(str(p), "before", "after")
        backup = Path(result["backup"])
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_text(), "before\n")
        self.assertTrue(str(backup).startswith(str(self.root / ".zero-backups")))

    def test_run_command_rejects_string(self):
        result = self.tools.run_command("echo hi")
        self.assertEqual(result["status"], "error")
        self.assertIn("argv list", result["message"])

    def test_run_command_timeout(self):
        result = self.tools.run_command(["sleep", "5"], timeout=1)
        self.assertEqual(result["status"], "error")
        self.assertIn("timed out", result["message"])

    def test_read_file_outside_root_denied(self):
        with self.assertRaises(PermissionError):
            self.tools.read_file("/etc/hosts")

    def test_symlink_escape_denied(self):
        # resolve-then-check must defeat a symlink pointing outside the root
        link = self.root / "sneaky"
        link.symlink_to("/etc")
        with self.assertRaises(PermissionError):
            self.tools.read_file(str(link / "hosts"))


if __name__ == "__main__":
    unittest.main()
