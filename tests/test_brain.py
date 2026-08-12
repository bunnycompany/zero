# zero/tests/test_brain.py

import os
import tempfile
import unittest

from brain.orchestrator import BrainOrchestrator


@unittest.skipUnless(os.environ.get("ZERO_RUN_MODEL_TESTS"), "loads the full MLX model; set ZERO_RUN_MODEL_TESTS=1")
class TestBrain(unittest.TestCase):
    def test_brain_loading_and_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ZERO_ROOT"] = tmp
            brain = BrainOrchestrator()
            response = brain.process_context("Testing the brain.")
            self.assertTrue(isinstance(response, str) and len(response) > 0)

if __name__ == "__main__":
    unittest.main()
