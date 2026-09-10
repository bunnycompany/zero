# zero/tests/test_tools.py
#
# The sed replacement: literal semantics, count guard, snapshots, timeouts.

import os
import shutil
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
        # a fake owner home, separate from the root (US-024 read widening)
        self._home = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = self._home.name
        self.home = Path(self._home.name).resolve()
        self.downloads = self.home / "Downloads"
        self.downloads.mkdir()
        self.tools = ToolDispatcher()

    def tearDown(self):
        if self._old_root is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old_root
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        self._tmp.cleanup()
        self._home.cleanup()

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

    # --- US-024: "what is in my Downloads" ---------------------------------

    def test_list_and_read_downloads_allowed(self):
        (self.downloads / "invoice.pdf").write_text("pdf")
        (self.downloads / "photos").mkdir()
        result = self.tools.list_dir("~/Downloads")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["entries"], ["invoice.pdf", "photos/"])
        result = self.tools.read_file("~/Downloads/invoice.pdf")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["content"], "pdf")

    @unittest.skipUnless(shutil.which("rg"), "ripgrep not installed")
    def test_search_scope_downloads_allowed(self):
        (self.downloads / "receipt.txt").write_text("total 42\n")
        result = self.tools.search_code("total", scope="~/Downloads")
        self.assertEqual(result["status"], "success")
        self.assertIn("receipt.txt", result["output"])

    def test_write_to_downloads_denied(self):
        # reads were widened; writes must still be confined to the root
        with self.assertRaises(PermissionError):
            self.tools.write_file("~/Downloads/note.txt", "x")
        self.assertFalse((self.downloads / "note.txt").exists())
        (self.downloads / "invoice.txt").write_text("keep")
        with self.assertRaises(PermissionError):
            self.tools.edit_file("~/Downloads/invoice.txt", "keep", "gone")
        self.assertEqual((self.downloads / "invoice.txt").read_text(), "keep")

    def test_downloads_traversal_escape_denied(self):
        for path in ("~/Downloads/../.ssh", "~/Downloads/../../etc", "~/Downloads/../"):
            with self.assertRaises(PermissionError, msg=path):
                self.tools.list_dir(path)

    def test_root_still_readable_after_widening(self):
        self._mk("notes.txt", "hello\n")
        self.assertEqual(self.tools.read_file("notes.txt")["content"], "hello\n")
        self.assertIn("notes.txt", self.tools.list_dir()["entries"])


if __name__ == "__main__":
    unittest.main()
