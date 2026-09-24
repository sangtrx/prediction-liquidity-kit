import unittest
from decimal import Decimal as D

from prediction_liquidity_kit.allocator import (
    MarketEconomics,
    adverse_selection_sensitivity,
    allocate_capital,
    decompose,
)


def market(market_id: str, **overrides: object) -> MarketEconomics:
    values: dict[str, object] = {
        "market_id": market_id,
        "theoretical_reward_rate": D("0.08"),
        "expected_realized_reward_rate": D("0.05"),
        "expected_spread_capture_rate": D("0.02"),
        "expected_fill_rate": D("0.50"),
        "fees_rate": D("0.01"),
        "adverse_selection_rate": D("0.01"),
        "inventory_risk_rate": D("0.003"),
        "capital_cost_rate": D("0.002"),
        "max_allocation": D("100"),
        "risk_cap": D("100"),
    }
    values.update(overrides)
    return MarketEconomics(**values)


class CapitalAllocatorTest(unittest.TestCase):
    def test_budget_and_market_risk_caps_bind_deterministically(self) -> None:
        best = market(
            "best",
            expected_realized_reward_rate=D("0.07"),
            expected_spread_capture_rate=D("0.03"),
            fees_rate=D("0.01"),
            adverse_selection_rate=D("0.005"),
            inventory_risk_rate=D("0.003"),
            capital_cost_rate=D("0.002"),
            risk_cap=D("30"),
        )
        second = market(
            "second",
            expected_realized_reward_rate=D("0.04"),
            expected_spread_capture_rate=D("0.02"),
            fees_rate=D("0.01"),
            adverse_selection_rate=D("0.005"),
            inventory_risk_rate=D("0.003"),
            capital_cost_rate=D("0.002"),
        )
        dominated = market(
            "dominated",
            expected_realized_reward_rate=D("0.01"),
            expected_spread_capture_rate=D("0.005"),
            fees_rate=D("0.01"),
            adverse_selection_rate=D("0.01"),
            inventory_risk_rate=D("0.005"),
            capital_cost_rate=D("0.002"),
        )

        result = allocate_capital([second, dominated, best], capital_budget=D("50"))

        self.assertEqual(result.allocated_capital, D("50"))
        self.assertEqual(result.unallocated_capital, D("0"))
        self.assertEqual(
            [(item.market_id, item.capital) for item in result.allocations],
            [("best", D("30")), ("second", D("20"))],
        )
        self.assertEqual(result.allocations[0].decomposition.net_expected_rate, D("0.080"))
        self.assertEqual(result.allocations[0].values.net_expected_value, D("2.400"))
        self.assertEqual(result.allocations[0].values.expected_filled_capital, D("15.00"))
        self.assertIn(
            ("dominated", "NON_POSITIVE_NET_EXPECTED_RATE"),
            [(item.market_id, item.reason) for item in result.skipped],
        )

    def test_unknown_risk_input_is_not_imputed(self) -> None:
        unknown = market("unknown-risk", risk_cap=None)

        result = allocate_capital([unknown], capital_budget=D("10"))

        self.assertEqual(result.allocated_capital, D("0"))
        self.assertEqual(result.unallocated_capital, D("10"))
        self.assertEqual(len(result.allocations), 0)
        self.assertEqual(result.skipped[0].reason, "UNKNOWN:risk_cap")

    def test_output_decomposes_expected_economics(self) -> None:
        item = market("m")

        parts = decompose(item)

        self.assertEqual(parts.theoretical_reward_rate, D("0.08"))
        self.assertEqual(parts.expected_realized_reward_rate, D("0.05"))
        self.assertEqual(parts.expected_spread_capture_rate, D("0.02"))
        self.assertEqual(parts.expected_fill_rate, D("0.50"))
        self.assertEqual(parts.fees_rate, D("0.01"))
        self.assertEqual(parts.adverse_selection_rate, D("0.01"))
        self.assertEqual(parts.inventory_risk_rate, D("0.003"))
        self.assertEqual(parts.capital_cost_rate, D("0.002"))
        self.assertEqual(parts.net_expected_rate, D("0.045"))

    def test_tied_rates_have_stable_market_id_order(self) -> None:
        result = allocate_capital(
            [market("b"), market("a")],
            capital_budget=D("150"),
        )

        self.assertEqual(
            [(item.market_id, item.capital) for item in result.allocations],
            [("a", D("100")), ("b", D("50"))],
        )

    def test_adverse_selection_sensitivity_is_explicit(self) -> None:
        points = adverse_selection_sensitivity(
            market("m"),
            [D("0"), D("1"), D("2")],
        )

        self.assertEqual(
            [point.net_expected_rate for point in points],
            [D("0.055"), D("0.045"), D("0.035")],
        )

    def test_invalid_expected_reward_fails_explicitly(self) -> None:
        invalid = market(
            "invalid",
            theoretical_reward_rate=D("0.04"),
            expected_realized_reward_rate=D("0.05"),
        )

        with self.assertRaisesRegex(ValueError, "cannot exceed theoretical"):
            allocate_capital([invalid], capital_budget=D("10"))

    def test_duplicate_market_ids_fail_explicitly(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate market_id"):
            allocate_capital([market("same"), market("same")], capital_budget=D("10"))


if __name__ == "__main__":
    unittest.main()
