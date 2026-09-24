from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from prediction_liquidity_kit.cli import main


class RulesCliTest(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, object]:
        output = io.StringIO()
        with patch("sys.argv", ["prediction-liquidity-kit", *args]), redirect_stdout(output):
            code = main()
        return code, json.loads(output.getvalue())

    def test_list_and_inspect(self) -> None:
        code, listed = self.run_cli("rules", "list")
        self.assertEqual(code, 0)
        versions = {item["version"] for item in listed}
        self.assertIn("kalshi-liquidity-help-2026-09-19", versions)
        self.assertIn("kalshi-volume-help-2026-08-05", versions)

        code, inspected = self.run_cli(
            "rules", "inspect", "kalshi-liquidity-help-2026-09-19"
        )
        self.assertEqual(code, 0)
        self.assertEqual(inspected["family"], "kalshi_liquidity_v1")

    def test_evaluate_selected_version(self) -> None:
        code, evaluated = self.run_cli(
            "rules",
            "evaluate",
            "kalshi-volume-help-2026-08-05",
            "--input-json",
            json.dumps(
                {
                    "contract_price": "0.50",
                    "user_eligible_contracts": "1000",
                    "total_eligible_contracts": "1000",
                    "reward_pool": "1000",
                }
            ),
        )
        self.assertEqual(code, 0)
        self.assertEqual(evaluated["theoretical_reward"], "5.00")


if __name__ == "__main__":
    unittest.main()
