# zero/tests/test_her_intake.py
#
# Her's getting-to-know-you process, wiring layer: paced questions, verbatim
# facts with provenance, skip/retire, and the main-loop hook that keeps an
# answer to Her out of decide() entirely. No MLX.

import json
import os
import tempfile
import unittest
from pathlib import Path

import main
from danger_core.executor import DangerCore
from her import intake, profile
from zero import consolidator, memory, ns, nspath


class RecordingBrain:
    """A brain that must NOT be asked to decide during an intake turn."""
    def __init__(self):
        self.decided = []
        self.extracted = []

    def decide(self, context, goal, manifest, memory=""):
        self.decided.append(goal)
        return {"tool": "no_op", "args": {}}, "scripted", None

    def extract_observations(self, goal, call, result):
        self.extracted.append(goal)
        return 0


class IntakeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old
        self._tmp.cleanup()

    def _events(self):
        return [json.loads(l) for l in nspath.journal().read_text().splitlines() if l.strip()]

    def test_first_question_is_the_name_and_is_idempotent(self):
        q = intake.next_question(now=1000.0)
        self.assertEqual(q["id"], "name")
        # asking again while it is pending opens nothing new
        self.assertEqual(intake.next_question(now=1500.0)["id"], "name")
        self.assertEqual(intake.pending()["id"], "name")

    def test_answer_becomes_verbatim_fact_with_provenance(self):
        intake.next_question(now=1000.0)
        reply = intake.turn({"text": "Dal", "reply_to": "name"}, now=1001.0)
        self.assertIn("Dal", reply)
        self.assertEqual(memory.drain_observations(), 1)
        fact = memory.load_facts()[0]
        self.assertEqual(fact["text"], "Wants to be called Dal")
        self.assertEqual(fact["origin"], "intake:name")
        self.assertEqual(fact["speaker"], "user")
        # the reply also opens the next question in the same breath
        self.assertIn(intake.DECK[1]["ask"], reply)

    def test_pace_caps_questions_per_day(self):
        now = 1000.0
        for i in range(intake.PACE_PER_DAY):
            q = intake.next_question(now=now + i)
            self.assertIsNotNone(q)
            intake.turn({"text": f"answer {i}", "reply_to": q["id"]}, now=now + i + 0.5)
        self.assertIsNone(intake.pending())
        self.assertIsNone(intake.next_question(now=now + 10))          # enough for today
        self.assertIsNotNone(intake.next_question(now=now + 86401))    # tomorrow

    def test_skip_moves_on_and_returns_a_week_later(self):
        intake.next_question(now=1000.0)
        reply = intake.turn({"text": "skip", "reply_to": "name"}, now=1001.0)
        self.assertIn("leave that one", reply)
        self.assertEqual(memory.drain_observations(), 0)  # nothing recorded
        self.assertEqual(intake.pending()["id"], "her_name")  # moved on
        # a week later the skipped question is eligible again
        state = intake.load()
        for qid in list(state["asked"]):
            if qid != "name":
                state["answered"][qid] = {"ts": 1002.0, "text": "x"}
        ns.write_doc("her/intake", "her", state)
        later = 1001.0 + intake.SKIP_RETRY_S + 1
        ids = []
        for _ in range(len(intake.DECK)):
            q = intake.next_question(now=later)
            if not q:
                break
            ids.append(q["id"])
            intake.turn({"text": "x", "reply_to": q["id"]}, now=later + 1)
            later += 86400
        self.assertIn("name", ids)

    def test_never_retires_the_question_for_good(self):
        intake.next_question(now=1000.0)
        intake.turn({"text": "never", "reply_to": "name"}, now=1001.0)
        self.assertIn("name", intake.load()["retired"])
        for day in range(20):
            q = intake.next_question(now=2000.0 + day * 86400)
            if q:
                self.assertNotEqual(q["id"], "name")
                intake.turn({"text": "x", "reply_to": q["id"]}, now=2001.0 + day * 86400)

    def test_main_loop_routes_reply_to_intake_not_decide(self):
        intake.next_question(now=1000.0)
        ns.submit_command("Dal", source="human", reply_to="name")
        brain = RecordingBrain()
        handled = main.handle_commands(brain, DangerCore())
        self.assertTrue(handled)
        self.assertEqual(brain.decided, [])            # never consulted for a decision
        self.assertEqual(len(brain.extracted), 1)      # but asked for extra facts
        events = self._events()
        kinds = [e["event"] for e in events]
        self.assertIn("intake_answered", kinds)
        self.assertIn("answered", kinds)
        self.assertNotIn("proposed", kinds)
        self.assertEqual(ns.read_doc("answer")["payload"]["goal"], "Dal")
        self.assertEqual(ns.read_text("status"), "idle")

    def test_plain_command_is_never_intercepted(self):
        intake.next_question(now=1000.0)
        ns.submit_command("what is in my downloads")  # no reply_to
        brain = RecordingBrain()
        main.handle_commands(brain, DangerCore())
        self.assertEqual(brain.decided, ["what is in my downloads"])
        self.assertIsNotNone(intake.pending())  # the question is still waiting

    def test_bad_reply_to_is_ignored(self):
        self.assertFalse(intake.handles({"text": "x", "reply_to": "not-a-question"}))
        self.assertFalse(intake.handles({"text": "x"}))

    def test_core_block_renders_only_what_the_user_said(self):
        intake.next_question(now=1000.0)
        intake.turn({"text": "Dal", "reply_to": "name"}, now=1001.0)
        # a brain-inferred fact must never be promoted into the pinned block
        memory.submit_observation("probably likes jazz", "music", 3)
        consolidator.run_once()
        core = memory.read_core()
        self.assertTrue(core.startswith(profile.HEADER))
        self.assertIn("Wants to be called Dal", core)
        self.assertNotIn("jazz", core)
        # and it is what decide() sees first
        self.assertTrue(memory.render({"app": "unknown"}, "hello").startswith(profile.HEADER))

    def test_forgetting_stamps_not_deletes(self):
        intake.next_question(now=1000.0)
        intake.turn({"text": "Dal", "reply_to": "name"}, now=1001.0)
        consolidator.run_once()
        fid = memory.load_facts()[0]["id"]
        self.assertTrue(memory.invalidate_fact(fid))
        self.assertEqual(memory.load_facts(), [])
        self.assertEqual(len(memory.load_facts(include_invalidated=True)), 1)
        consolidator.refresh_core()
        self.assertEqual(memory.read_core(), "")  # the block follows the facts
        self.assertFalse(memory.invalidate_fact(fid))  # already stamped


if __name__ == "__main__":
    unittest.main()
