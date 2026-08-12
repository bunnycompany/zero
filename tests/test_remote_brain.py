# zero/tests/test_remote_brain.py
#
# The gateway brain exists because this machine (8 GB) cannot load the bigger
# gemma-4 variants at all — 12B is 8.3 GB of weights. Contract: same interface
# as the local brain, and a dead gateway is a failed turn, never a crash.

import unittest
from unittest import mock

from brain.remote import RemoteBrain, build_brain
from brain.orchestrator import BrainOrchestrator


class RemoteBrainTestCase(unittest.TestCase):
    def _brain(self):
        return RemoteBrain(base_url="https://example.test/v1", api_key="k")

    def test_same_interface_as_local(self):
        for name in ("decide", "extract_observations", "_generate"):
            self.assertTrue(callable(getattr(self._brain(), name)))

    def test_gateway_failure_returns_unreachable_sentinel_not_raise(self):
        # A dead gateway is a failed turn, never a crash — and now a DISTINCT
        # failure the answer layer can phrase honestly ("I can't reach the
        # server") instead of a confusing parse error. _post is retried a few
        # times first (transient 500/530s were the real-world symptom), so
        # patch _post itself to fail every time.
        from brain.orchestrator import GATEWAY_UNREACHABLE
        b = self._brain()
        with mock.patch.object(b, "_post", side_effect=OSError("network down")):
            self.assertEqual(b._generate("p", 10), GATEWAY_UNREACHABLE)

    def test_transient_failure_then_success_is_retried(self):
        # One blip, then a good response: the retry must recover it rather than
        # give up on the first error.
        b = self._brain()
        good = {"choices": [{"message": {"content": "recovered"}}]}
        with mock.patch.object(b, "_post", side_effect=[OSError("blip"), good]):
            self.assertEqual(b._generate("p", 10), "recovered")

    def test_client_error_is_not_retried(self):
        # A 4xx will never improve; it must be raised through immediately, not
        # retried, so a bad request/auth fails fast.
        import urllib.error
        b = self._brain()
        calls = {"n": 0}
        def raise_400(_payload):
            calls["n"] += 1
            raise urllib.error.HTTPError("u", 400, "bad", {}, None)
        with mock.patch.object(b, "_post", side_effect=raise_400):
            from brain.orchestrator import GATEWAY_UNREACHABLE
            self.assertEqual(b._generate("p", 10), GATEWAY_UNREACHABLE)
        self.assertEqual(calls["n"], 1)  # tried once, not three times

    def test_malformed_response_returns_empty(self):
        b = self._brain()
        with mock.patch.object(b, "_post", return_value={"nope": True}):
            self.assertEqual(b._generate("p", 10), "")

    def test_reasoning_only_response_is_not_mistaken_for_an_answer(self):
        b = self._brain()
        payload = {"choices": [{"message": {"content": "", "reasoning_content": "hmm..."}}]}
        with mock.patch.object(b, "_post", return_value=payload):
            self.assertEqual(b._generate("p", 10), "")

    def test_extracts_content(self):
        b = self._brain()
        payload = {"choices": [{"message": {"content": "hello"}}]}
        with mock.patch.object(b, "_post", return_value=payload):
            self.assertEqual(b._generate("p", 10), "hello")

    def test_build_brain_picks_by_env(self):
        with mock.patch.dict("os.environ", {"ZERO_BRAIN": "remote", "ZERO_API_KEY": "k"}, clear=False):
            self.assertIsInstance(build_brain(), RemoteBrain)
        with mock.patch.dict("os.environ", {"ZERO_BRAIN": "local"}, clear=False):
            with mock.patch.object(BrainOrchestrator, "__init__", lambda self: None):
                self.assertNotIsInstance(build_brain(), RemoteBrain)

    def test_api_key_never_appears_in_repr(self):
        self.assertNotIn("k", repr(self._brain()).replace("Brain", ""))


if __name__ == "__main__":
    unittest.main()
