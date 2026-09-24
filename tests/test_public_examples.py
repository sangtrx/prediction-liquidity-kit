from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicExamplesTest(unittest.TestCase):
    def test_public_examples_run_from_clean_checkout(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(ROOT / "examples" / "public_examples.py")],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertIn("simulation-only", payload["boundary"])
        self.assertEqual(payload["evidence"]["rule_inputs"], "synthetic")
        self.assertEqual(payload["evidence"]["sponsor_calibration"], "synthetic")
        self.assertFalse(payload["replay"]["profitability_claim_allowed"])
        self.assertEqual(payload["capital_allocation"]["allocated_capital"], "30")
        self.assertEqual(payload["sponsor_simulation"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
