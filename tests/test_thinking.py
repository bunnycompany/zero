# zero/tests/test_thinking.py
#
# Dynamic thinking: reasoning is worth its tokens for decisions, and actively
# harmful for one-sentence language jobs (verified live — the model spent a
# whole 400-token budget thinking and leaked raw chain-of-thought to the user).

import unittest

from brain.orchestrator import BrainOrchestrator


class FakeTokenizer:
    def __init__(self):
        self.calls = []

    def apply_chat_template(self, messages, tokenize=False,
                            add_generation_prompt=True, enable_thinking=None):
        self.calls.append(enable_thinking)
        return "<|think|>P" if enable_thinking else "P"


class LegacyTokenizer:
    """A template that doesn't know the flag — must still work."""
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        return "P"


class ThinkingTestCase(unittest.TestCase):
    def _brain(self, tokenizer):
        brain = BrainOrchestrator.__new__(BrainOrchestrator)  # no model load
        brain.tokenizer = tokenizer
        brain.model = None
        brain.model_path = "test"
        import brain.orchestrator as mod
        self._real_generate = mod.generate
        mod.generate = lambda *a, **k: "out"
        self.addCleanup(lambda: setattr(mod, "generate", self._real_generate))
        return brain

    def test_thinking_off_by_default(self):
        tok = FakeTokenizer()
        self._brain(tok)._generate("p", 10)
        self.assertEqual(tok.calls, [False])

    def test_thinking_opt_in(self):
        tok = FakeTokenizer()
        self._brain(tok)._generate("p", 10, think=True)
        self.assertEqual(tok.calls, [True])

    def test_legacy_template_still_generates(self):
        self.assertEqual(self._brain(LegacyTokenizer())._generate("p", 10, think=True), "out")


if __name__ == "__main__":
    unittest.main()
