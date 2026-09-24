import unittest
import prediction_liquidity_kit
from prediction_liquidity_kit.cli import build_parser

class BootstrapTest(unittest.TestCase):
    def test_version_and_cli_import(self) -> None:
        self.assertEqual(prediction_liquidity_kit.__version__, "0.1.0")
        self.assertEqual(build_parser().prog, "prediction-liquidity-kit")

if __name__ == "__main__":
    unittest.main()
