from __future__ import annotations
import argparse
from prediction_liquidity_kit import __version__

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prediction-liquidity-kit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser

def main() -> int:
    build_parser().parse_args()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
