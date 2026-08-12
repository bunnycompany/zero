# zero/tests/test_answer.py
#
# The answer channel's contract: every turn speaks, failures included, and
# the model is never allowed to cause silence. (The previous prototype died
# of silence: "I'm not reading allat tool call crap".)

import unittest

from brain import answer


class FallbackTestCase(unittest.TestCase):
    def test_speaks_on_unparseable_decision(self):
        text = answer.fallback("do a thing", None, None)
        self.assertTrue(text and "another way" in text)

    def test_speaks_on_tool_error(self):
        result = {"status": "success", "result": {"status": "error", "message": "No such file"}}
        text = answer.fallback("read notes.txt", {"tool": "read_file", "args": {}}, result)
        self.assertIn("No such file", text)
        self.assertNotIn("{", text)  # no raw payloads in a human answer

    def test_explains_no_op_reason(self):
        call = {"tool": "no_op", "args": {"reason": "nothing needed doing"}}
        self.assertIn("nothing needed doing", answer.fallback("thanks!", call, None))

    def test_explains_shadow_mode_plainly(self):
        # the shape danger_core actually returns for a shadowed mutation
        result = {"status": "shadowed", "message": "write_file (write) not executed"}
        text = answer.fallback("delete everything", {"tool": "write_file", "args": {}}, result)
        self.assertIn("shadow", text.lower())

    def test_never_empty_and_bounded(self):
        for call in (None, {"tool": "no_op", "args": {}}, {"tool": "list_dir", "args": {"path": "."}}):
            text = answer.fallback("x", call, {"status": "success", "result": "y" * 5000})
            self.assertTrue(text.strip())
            self.assertLessEqual(len(text), answer.MAX_ANSWER_CHARS + 100)

    def test_compose_falls_back_when_model_raises(self):
        class Broken:
            def _generate(self, *a, **k):
                raise RuntimeError("model exploded")
        text = answer.compose(Broken(), "do it", {"tool": "list_dir", "args": {}}, None)
        self.assertTrue(text.strip())  # spoke anyway

    def test_compose_rejects_json_shaped_output(self):
        class JsonBrain:
            def _generate(self, *a, **k):
                return '{"tool": "list_dir"}'
        text = answer.compose(JsonBrain(), "do it", {"tool": "list_dir", "args": {}}, None)
        self.assertFalse(text.startswith("{"))  # fell back to English


if __name__ == "__main__":
    unittest.main()


class SpeakableTestCase(unittest.TestCase):
    """Live regression: gemma-4 spent its whole budget in an unclosed thought
    block and the raw reasoning reached the user. Never again."""

    def test_rejects_unclosed_thought_block(self):
        leaked = "<|channel>thought\nThinking Process:\n\n1. Analyze the Request"
        self.assertFalse(answer.is_speakable(leaked))

    def test_rejects_json_and_empties(self):
        for bad in ("", "   ", "{}", '{"tool": "x"}', "[]", "hi"):
            self.assertFalse(answer.is_speakable(bad), msg=repr(bad))

    def test_accepts_a_real_sentence(self):
        for good in ("Done — I listed the folder and found 12 files.",
                     "I couldn't find that file, want me to search elsewhere?"):
            self.assertTrue(answer.is_speakable(good), msg=good)

    def test_compose_falls_back_on_leaked_reasoning(self):
        class Thinker:
            def _generate(self, *a, **k):
                return "<|channel>thought\nThinking Process: the user wants"
        text = answer.compose(Thinker(), "list files", {"tool": "list_dir", "args": {}}, None)
        self.assertTrue(answer.is_speakable(text))
        self.assertNotIn("channel", text)


class RealResultShapesTestCase(unittest.TestCase):
    """Shapes taken from danger_core's actual returns, caught in live testing:
    the fallback said 'I write fileed' and pasted a raw dict at the user."""

    SHADOWED = {"status": "shadowed",
                "message": "write_file (write) not executed in mode 'shadow'"}
    ERROR = {"status": "success",
             "result": {"status": "error", "message": "[Errno 2] No such file"}}
    OK_LIST = {"status": "success", "result": ["a.txt", "b.txt"]}

    def test_shadow_explained_without_payload(self):
        text = answer.fallback("save a note", {"tool": "write_file", "args": {}}, self.SHADOWED)
        self.assertIn("shadow mode", text)
        self.assertNotIn("{", text)
        self.assertNotIn("status", text)

    def test_no_mangled_verbs(self):
        for tool in ("write_file", "read_file", "list_dir", "edit_file", "run_command"):
            text = answer.fallback("x", {"tool": tool, "args": {}}, self.OK_LIST)
            self.assertNotIn("fileed", text)
            self.assertNotIn("_", text)

    def test_error_offers_a_next_step(self):
        text = answer.fallback("read gone.txt", {"tool": "read_file", "args": {}}, self.ERROR)
        self.assertIn("No such file", text)
        self.assertIn("try", text.lower())

    def test_success_is_readable(self):
        text = answer.fallback("list files", {"tool": "list_dir", "args": {}}, self.OK_LIST)
        self.assertTrue(text.startswith("Done"))
        self.assertNotIn("{", text)
