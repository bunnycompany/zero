# zero/tests/test_parse.py

import unittest

from brain import parse


class ParseTestCase(unittest.TestCase):
    def test_clean_json(self):
        call, err = parse.extract_tool_call('{"tool": "read_file", "args": {"path": "x"}}')
        self.assertIsNone(err)
        self.assertEqual(call, {"tool": "read_file", "args": {"path": "x"}})

    def test_fenced_json(self):
        text = 'Sure! Here you go:\n```json\n{"tool": "no_op", "args": {}}\n```\nHope that helps.'
        call, err = parse.extract_tool_call(text)
        self.assertIsNone(err)
        self.assertEqual(call["tool"], "no_op")

    def test_thought_channel_stripped(self):
        # reasoning checkpoints emit <|channel>thought ... <channel|> before
        # the answer — the draft inside the thought block must NOT win
        text = (
            '<|channel>thought\nI could call {"tool": "run_command", "args": {"cmd": ["rm"]}}'
            ' but no.\n<channel|>{"tool": "no_op", "args": {"reason": "nothing to do"}}'
        )
        call, err = parse.extract_tool_call(text)
        self.assertIsNone(err)
        self.assertEqual(call["tool"], "no_op")

    def test_args_default_to_empty(self):
        call, err = parse.extract_tool_call('{"tool": "no_op"}')
        self.assertIsNone(err)
        self.assertEqual(call["args"], {})

    def test_garbage_returns_reason_not_exception(self):
        call, err = parse.extract_tool_call("I think you should organize your files!")
        self.assertIsNone(call)
        self.assertIsNotNone(err)

    def test_non_dict_args_rejected(self):
        call, err = parse.extract_tool_call('{"tool": "no_op", "args": "yes"}')
        self.assertIsNone(call)

    def test_extract_code_prefers_last_fence(self):
        text = "```python\ndraft = 1\n```\nActually:\n```python\nfinal = 2\n```"
        self.assertEqual(parse.extract_code(text), "final = 2")


if __name__ == "__main__":
    unittest.main()
