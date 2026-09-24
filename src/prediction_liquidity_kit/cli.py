from __future__ import annotations

import argparse
import json
import sys

from prediction_liquidity_kit import __version__
from prediction_liquidity_kit.rules import RuleError, builtin_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prediction-liquidity-kit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    commands = parser.add_subparsers(dest="command")
    rules = commands.add_parser("rules", help="inspect and evaluate versioned reward rules")
    rule_commands = rules.add_subparsers(dest="rules_command", required=True)

    rule_commands.add_parser("list", help="list admitted rule versions")

    inspect_parser = rule_commands.add_parser("inspect", help="inspect one exact rule version")
    inspect_parser.add_argument("version")

    evaluate_parser = rule_commands.add_parser("evaluate", help="evaluate one exact rule version")
    evaluate_parser.add_argument("version")
    evaluate_parser.add_argument(
        "--input-json",
        required=True,
        help="JSON object containing the selected rule family's explicit inputs",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        return 0

    registry = builtin_registry()
    try:
        if args.rules_command == "list":
            payload = [rule.to_dict() for rule in registry.list()]
        elif args.rules_command == "inspect":
            payload = registry.get(args.version).to_dict()
        elif args.rules_command == "evaluate":
            try:
                inputs = json.loads(args.input_json)
            except json.JSONDecodeError as exc:
                raise RuleError(f"input JSON is invalid: {exc.msg}") from exc
            if not isinstance(inputs, dict):
                raise RuleError("input JSON must be an object")
            payload = registry.evaluate(args.version, inputs)
        else:
            raise RuleError("unsupported rules command")
    except RuleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
