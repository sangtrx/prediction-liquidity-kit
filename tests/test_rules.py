from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import unittest

from prediction_liquidity_kit.rules import (
    BUILTIN_RULES,
    RuleError,
    RuleNotFound,
    RuleRegistry,
    builtin_registry,
)


class RuleRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = builtin_registry()

    def test_source_snapshots_match_admitted_hashes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for rule in BUILTIN_RULES:
            payload = (root / rule.source_snapshot_path).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), rule.source_snapshot_sha256)

    def test_kalshi_liquidity_public_payout_example(self) -> None:
        result = self.registry.evaluate(
            "kalshi-liquidity-help-2026-09-19",
            {
                "target_size": "1000",
                "discount_factor": "0.90",
                "order_size": "100",
                "ticks_away": 1,
                "user_period_score": "20",
                "all_period_score": "100",
                "reward_pool": "100",
                "non_excluded_snapshots": 8000,
                "total_snapshots": 10000,
            },
        )
        self.assertEqual(result["raw_order_score"], "90.00")
        self.assertEqual(result["period_share"], "0.2")
        self.assertEqual(result["theoretical_reward"], "16.00")
        self.assertEqual(result["payable_reward"], "16.00")

    def test_kalshi_volume_public_examples(self) -> None:
        uncapped = self.registry.evaluate(
            "kalshi-volume-help-2026-08-05",
            {
                "contract_price": "0.50",
                "user_eligible_contracts": "100000",
                "total_eligible_contracts": "1000000",
                "reward_pool": "1000",
            },
        )
        self.assertEqual(uncapped["volume_share"], "0.1")
        self.assertEqual(uncapped["theoretical_reward"], "100.00")

        capped = self.registry.evaluate(
            "kalshi-volume-help-2026-08-05",
            {
                "contract_price": "0.50",
                "user_eligible_contracts": "1000",
                "total_eligible_contracts": "1000",
                "reward_pool": "1000",
            },
        )
        self.assertEqual(capped["per_contract_cap_reward"], "5.00")
        self.assertEqual(capped["theoretical_reward"], "5.00")

    def test_zero_user_participation_yields_zero_reward(self) -> None:
        liquidity = self.registry.evaluate(
            "kalshi-liquidity-help-2026-09-19",
            {
                "target_size": "1000",
                "discount_factor": "0.90",
                "order_size": "100",
                "ticks_away": 1,
                "user_period_score": "0",
                "all_period_score": "100",
                "reward_pool": "100",
                "non_excluded_snapshots": 8000,
                "total_snapshots": 10000,
            },
        )
        self.assertEqual(liquidity["period_share"], "0")
        self.assertEqual(liquidity["theoretical_reward"], "0.00")
        self.assertEqual(liquidity["payable_reward"], "0.00")

        volume = self.registry.evaluate(
            "kalshi-volume-help-2026-08-05",
            {
                "contract_price": "0.50",
                "user_eligible_contracts": "0",
                "total_eligible_contracts": "1000",
                "reward_pool": "1000",
            },
        )
        self.assertEqual(volume["volume_share"], "0")
        self.assertEqual(volume["proportional_reward"], "0.00")
        self.assertEqual(volume["per_contract_cap_reward"], "0.00")
        self.assertEqual(volume["theoretical_reward"], "0.00")

    def test_registry_resolves_historical_versions_without_latest_alias(self) -> None:
        current = self.registry.get("kalshi-liquidity-help-2026-09-19")
        prior = replace(
            current,
            version="kalshi-liquidity-synthetic-prior-fixture",
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            effective_to=datetime(2026, 9, 19, tzinfo=timezone.utc),
            notes="Synthetic registry regression fixture only; not an admitted venue rule.",
        )
        registry = RuleRegistry([prior, current])
        self.assertEqual(
            registry.resolve(
                venue="kalshi",
                program="liquidity_incentive",
                at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            ).version,
            prior.version,
        )
        self.assertEqual(
            registry.resolve(
                venue="kalshi",
                program="liquidity_incentive",
                at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            ).version,
            current.version,
        )

    def test_invalid_or_missing_inputs_fail_explicitly(self) -> None:
        with self.assertRaisesRegex(RuleError, "target_size"):
            self.registry.evaluate(
                "kalshi-liquidity-help-2026-09-19",
                {
                    "discount_factor": "0.9",
                    "order_size": "100",
                    "ticks_away": 0,
                    "user_period_score": "1",
                    "all_period_score": "1",
                    "reward_pool": "10",
                    "non_excluded_snapshots": 1,
                    "total_snapshots": 1,
                },
            )
        with self.assertRaisesRegex(RuleError, "unsupported"):
            self.registry.evaluate(
                "kalshi-volume-help-2026-08-05",
                {
                    "contract_price": "0.01",
                    "user_eligible_contracts": "100",
                    "total_eligible_contracts": "100",
                    "reward_pool": "10",
                },
            )
        with self.assertRaises(RuleNotFound):
            self.registry.get("latest")


if __name__ == "__main__":
    unittest.main()
