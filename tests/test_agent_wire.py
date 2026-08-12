# zero/tests/test_agent_wire.py
#
# Layer-1 wire eval: the REAL agent step (main.handle_commands) with the REAL
# executor against a sandbox namespace — only the brain is scripted. This is
# the test that was impossible before the seams existed: it proves command →
# decision → dispatch → journal end to end, in milliseconds, with no MLX.

import json
import os
import tempfile
import unittest
from pathlib import Path

import main
from danger_core.executor import DangerCore
from zero import memory, ns, nspath


class ScriptedBrain:
    """Stands in for BrainOrchestrator.decide with a fixed decision."""

    def __init__(self, call=None, raw="scripted", err=None):
        self.call = call
        self.raw = raw
        self.err = err
        self.seen = []

    def decide(self, context, goal, manifest):
        self.seen.append({"context": context, "goal": goal, "manifest": manifest})
        if self.call is not None:
            ns.write_doc("action", "brain", dict(self.call, model="scripted"))
        return self.call, self.raw, self.err


class AgentWireTestCase(unittest.TestCase):
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

    def _journal_events(self):
        journal = nspath.journal()
        if not journal.exists():
            return []
        return [json.loads(l) for l in journal.read_text().strip().split("\n")]

    def test_no_commands_means_no_step(self):
        brain = ScriptedBrain(call={"tool": "no_op", "args": {}})
        self.assertFalse(main.handle_commands(brain, self.executor))
        self.assertEqual(brain.seen, [])  # the brain was never consulted

    def test_command_reaches_brain_and_tool_executes(self):
        target = self.root / "note.txt"
        target.write_text("remember the milk")
        ns.submit_command("what's in my note?")

        brain = ScriptedBrain(call={"tool": "read_file", "args": {"path": str(target)}})
        handled = main.handle_commands(brain, self.executor)

        self.assertTrue(handled)
        # the user's text reached the brain — the old intent/current
        # write-write collision made exactly this impossible
        self.assertEqual(brain.seen[0]["goal"], "what's in my note?")
        events = {e["event"] for e in self._journal_events()}
        self.assertIn("command_received", events)
        self.assertIn("executed", events)
        self.assertEqual(ns.read_text("status"), "idle")  # loop settles

    def test_write_is_shadowed_end_to_end_by_default(self):
        target = self.root / "config.txt"
        target.write_text("a|b")
        ns.submit_command("replace a|b with c")

        brain = ScriptedBrain(
            call={"tool": "edit_file", "args": {"path": str(target), "old_text": "a|b", "new_text": "c"}}
        )
        main.handle_commands(brain, self.executor)

        self.assertEqual(target.read_text(), "a|b")  # untouched in shadow
        events = {e["event"] for e in self._journal_events()}
        self.assertIn("shadowed", events)

    def test_unparseable_decision_is_journaled_not_fatal(self):
        ns.submit_command("do something")
        brain = ScriptedBrain(call=None, raw="I suggest organizing your files!", err="no JSON")
        handled = main.handle_commands(brain, self.executor)
        self.assertTrue(handled)
        events = {e["event"] for e in self._journal_events()}
        self.assertIn("decision_unparseable", events)
        self.assertEqual(ns.read_text("status"), "idle")

    def test_stale_context_falls_back(self):
        ns.submit_command("hello")
        brain = ScriptedBrain(call={"tool": "no_op", "args": {}})
        main.handle_commands(brain, self.executor)
        self.assertEqual(brain.seen[0]["context"], {"app": "unknown"})

    def test_fresh_context_is_used(self):
        ns.write_doc("context", "observer", {"app": "Mail", "bundle_id": "com.apple.mail"})
        ns.submit_command("hello")
        brain = ScriptedBrain(call={"tool": "no_op", "args": {}})
        main.handle_commands(brain, self.executor)
        self.assertEqual(brain.seen[0]["context"]["app"], "Mail")

    def test_idle_heartbeat_drains_memory_queue_into_facts(self):
        # Without this wiring, memory.submit_observation() queues forever and
        # zero.memory.render() (reads facts.ndjson, not the inbox) never sees
        # it — the whole continuous-learning loop is a silent no-op.
        memory.submit_observation("prefers the ~/.venv python", "python", 8)
        self.assertEqual(memory.load_facts(), [])  # queued, not yet a fact

        main.idle_heartbeat()

        facts = memory.load_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["text"], "prefers the ~/.venv python")
        self.assertEqual(ns.read_text("status"), "idle")


if __name__ == "__main__":
    unittest.main()
