# zero/tests/test_her_cli.py
#
# The `her` command against a sandbox: every non-interactive subcommand
# runs, speaks plainly, and the writes it makes are the human's own (a
# pairing, a revocation, a strike-out) — never the agent's channels.

import contextlib
import io
import os
import tempfile
import unittest

from her import cli, devices, intake, presence
from zero import consolidator, memory, ns


class CliTestCase(unittest.TestCase):
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

    def _run(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_bare_her_on_a_fresh_install_teaches(self):
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("don't know you yet", out)
        self.assertIn("isn't awake", out)

    def test_help_and_status_and_level(self):
        for args in (("help",), ("status",), ("level",), ("devices",), ("unsent",), ("profile",)):
            code, out = self._run(*args)
            self.assertEqual(code, 0, args)
            self.assertTrue(out.strip(), args)
            self.assertNotIn("Traceback", out)
        self.assertIn("echo ambient > namespace/control/presence", self._run("level")[1])

    def test_answer_goes_to_the_open_question_with_reply_to(self):
        intake.next_question()
        code, out = self._run("Dal")
        self.assertEqual(code, 0)
        cmds = ns.take_commands_full()
        self.assertEqual(cmds[0]["text"], "Dal")
        self.assertEqual(cmds[0]["reply_to"], "name")
        self.assertEqual(cmds[0]["source"], "human")
        self.assertIn("waiting for her", out)  # agent asleep: honest, not an error

    def test_plain_ask_has_no_reply_to_when_nothing_is_open(self):
        self._run("what", "is", "in", "my", "downloads")
        cmds = ns.take_commands_full()
        self.assertEqual(cmds[0]["text"], "what is in my downloads")
        self.assertNotIn("reply_to", cmds[0])

    def test_skip_with_nothing_open_is_a_noop(self):
        code, out = self._run("skip")
        self.assertEqual(code, 0)
        self.assertEqual(ns.take_commands(), [])
        self.assertIn("Nothing to skip", out)

    def test_glasses_mints_a_link_once_and_devices_lists_it(self):
        code, out = self._run("glasses")
        self.assertEqual(code, 0)
        self.assertIn("/glasses/?t=", out)
        token = out.split("?t=")[1].split()[0]
        self.assertIsNotNone(devices.authenticate(token))
        self.assertNotIn(token, str(devices.list_devices()))
        code, out = self._run("devices")
        self.assertIn("glasses", out)
        did = next(iter(devices.list_devices()))
        self.assertEqual(self._run("forget-device", did)[0], 0)
        self.assertIsNone(devices.authenticate(token))
        self.assertEqual(self._run("forget-device", did)[0], 1)

    def test_profile_and_forget(self):
        intake.next_question()
        intake.turn({"text": "Dal", "reply_to": "name"})
        memory.submit_observation("maybe likes jazz", "music", 2)
        consolidator.run_once()
        code, out = self._run("profile")
        self.assertIn("you said", out)
        self.assertIn("inferred", out)
        fid = [f["id"] for f in memory.load_facts() if f["text"] == "Wants to be called Dal"][0]
        self.assertEqual(self._run("forget", fid)[0], 0)
        self.assertNotIn("Dal", memory.read_core())
        self.assertEqual(self._run("forget", fid)[0], 1)

    def test_unsent_lists_and_review_needs_a_terminal(self):
        presence.would_say("You told me Theo's birthday is Saturday.", "date", "k")
        code, out = self._run("unsent")
        self.assertIn("Theo", out)
        code, out = self._run("review")
        self.assertEqual(code, 1)  # stdin is not a tty under the test runner
        self.assertEqual(presence.precision(), (0, 0.0))


if __name__ == "__main__":
    unittest.main()
