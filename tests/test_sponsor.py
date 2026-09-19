import unittest
from decimal import Decimal

from prediction_liquidity_kit.sponsor import (
    Calibration,
    LiquidityTarget,
    MarketBudgetRequest,
    ResponsePoint,
    interpolate_response,
    optimize_sponsor_budget,
)


D = Decimal


def calibration(*, sample_size: int = 20, uncertainty: str = "0.10") -> Calibration:
    return Calibration(
        points=(
            ResponsePoint(D("0"), D("20"), D("100"), D("0.80")),
            ResponsePoint(D("10"), D("10"), D("200"), D("0.95")),
        ),
        sample_size=sample_size,
        uncertainty_fraction=D(uncertainty),
        evidence_kind="synthetic",
    )


def request(
    market_id: str = "mkt-a",
    *,
    sample_size: int = 20,
    current: str = "5",
    max_reward: str = "10",
    max_change: str = "5",
    periods: int = 2,
) -> MarketBudgetRequest:
    return MarketBudgetRequest(
        market_id=market_id,
        target=LiquidityTarget(
            max_spread_bps=D("13.2"),
            min_depth=D("135"),
            min_quote_uptime=D("0.81"),
        ),
        calibration=calibration(sample_size=sample_size),
        current_reward_per_period=D(current),
        max_reward_per_period=D(max_reward),
        max_rate_change_per_period=D(max_change),
        periods=periods,
    )


class SponsorOptimizerTest(unittest.TestCase):
    def test_piecewise_linear_interpolation_recovers_known_curve(self) -> None:
        estimate = interpolate_response(calibration(), D("5"))
        self.assertEqual(estimate.spread_bps, D("15"))
        self.assertEqual(estimate.depth, D("150"))
        self.assertEqual(estimate.quote_uptime, D("0.875"))

    def test_chooses_minimum_conservative_reward_and_exposes_uncertainty(self) -> None:
        plan = optimize_sponsor_budget([request()], total_budget=D("20"))

        self.assertEqual(plan.status, "ok")
        self.assertEqual(plan.expected_spend, D("16"))
        self.assertEqual(len(plan.decisions), 1)

        decision = plan.decisions[0]
        self.assertEqual(decision.reward_per_period, D("8"))
        self.assertEqual(decision.expected_spend, D("16"))
        self.assertIn("association-only", decision.qualification)

        chosen_row = next(
            row for row in decision.sensitivity if row.reward_per_period == D("8")
        )
        self.assertEqual(chosen_row.bounds.spread_bps_upper, D("13.20"))
        self.assertTrue(chosen_row.conservative_target_met)

    def test_sparse_calibration_fails_closed_without_exploratory_mode(self) -> None:
        plan = optimize_sponsor_budget(
            [request(sample_size=4)],
            total_budget=D("20"),
        )

        self.assertEqual(plan.status, "no_decision")
        self.assertEqual(plan.decisions, ())
        self.assertIn("insufficient calibration", plan.reason or "")

    def test_sparse_calibration_can_be_explicitly_exploratory(self) -> None:
        plan = optimize_sponsor_budget(
            [request(sample_size=4)],
            total_budget=D("20"),
            exploratory=True,
        )

        self.assertEqual(plan.status, "exploratory")
        self.assertEqual(plan.decisions[0].reward_per_period, D("8"))
        self.assertIn("exploratory only", plan.decisions[0].qualification)

    def test_hard_budget_is_never_exceeded(self) -> None:
        plan = optimize_sponsor_budget([request()], total_budget=D("15"))

        self.assertEqual(plan.status, "no_decision")
        self.assertEqual(plan.expected_spend, D("0"))
        self.assertEqual(plan.decisions, ())
        self.assertEqual(plan.reason, "hard sponsor budget would be exceeded")

    def test_per_period_rate_change_cap_can_make_target_infeasible(self) -> None:
        plan = optimize_sponsor_budget(
            [request(current="0", max_change="7")],
            total_budget=D("20"),
        )

        self.assertEqual(plan.status, "no_decision")
        self.assertEqual(plan.decisions, ())
        self.assertIn("rate caps", plan.reason or "")

    def test_allocates_deterministically_across_markets_and_time(self) -> None:
        plan = optimize_sponsor_budget(
            [
                request("mkt-b", periods=1),
                request("mkt-a", periods=2),
            ],
            total_budget=D("30"),
        )

        self.assertEqual(plan.status, "ok")
        self.assertEqual([d.market_id for d in plan.decisions], ["mkt-a", "mkt-b"])
        self.assertEqual([d.reward_per_period for d in plan.decisions], [D("8"), D("8")])
        self.assertEqual(plan.expected_spend, D("24"))


if __name__ == "__main__":
    unittest.main()
