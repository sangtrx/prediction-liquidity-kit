import unittest
from decimal import Decimal

from prediction_liquidity_kit.controller import (
    ControllerConfig,
    LiquidityMeasurement,
    initial_state,
    replay_controller,
)


D = Decimal


def config(*, budget: str = "100") -> ControllerConfig:
    return ControllerConfig(
        target_low=D("10"),
        target_high=D("12"),
        max_incentive=D("5"),
        max_step_change=D("1"),
        total_budget=D(budget),
        confirmation_steps=2,
        stale_after_steps=1,
    )


class LiquidityControllerTest(unittest.TestCase):
    def test_stable_response_reaches_target_without_chatter(self) -> None:
        decisions = replay_controller(
            config(),
            [
                LiquidityMeasurement(D("8")),
                LiquidityMeasurement(D("8")),
                LiquidityMeasurement(D("10.5")),
                LiquidityMeasurement(D("11")),
            ],
            initial_incentive=D("1"),
        )

        self.assertEqual(
            [d.applied_incentive for d in decisions],
            [D("1"), D("2"), D("2"), D("2")],
        )
        self.assertEqual(decisions[-1].status, "ok")
        self.assertIn("deadband", decisions[-1].reason)

    def test_delayed_response_remains_bounded(self) -> None:
        decisions = replay_controller(
            config(),
            [LiquidityMeasurement(D(v)) for v in ("8", "8", "8", "8", "10.5")],
            initial_incentive=D("1"),
        )

        self.assertEqual(
            [d.applied_incentive for d in decisions],
            [D("1"), D("2"), D("3"), D("4"), D("4")],
        )
        self.assertTrue(all(d.applied_incentive <= D("5") for d in decisions))
        self.assertTrue(
            all(
                abs(d.applied_incentive - d.previous_incentive) <= D("1")
                for d in decisions
            )
        )

    def test_noisy_single_observations_do_not_drive_oscillation(self) -> None:
        decisions = replay_controller(
            config(),
            [
                LiquidityMeasurement(D("8")),
                LiquidityMeasurement(D("13")),
                LiquidityMeasurement(D("8")),
                LiquidityMeasurement(D("13")),
                LiquidityMeasurement(D("8")),
                LiquidityMeasurement(D("13")),
            ],
            initial_incentive=D("1"),
        )

        self.assertEqual([d.applied_incentive for d in decisions], [D("1")] * 6)
        self.assertTrue(all(d.outside_streak == 1 for d in decisions))

    def test_nonresponsive_market_obeys_budget_and_step_caps(self) -> None:
        decisions = replay_controller(
            config(budget="20"),
            [LiquidityMeasurement(D("8")) for _ in range(12)],
        )

        total_spend = sum((d.spend for d in decisions), D("0"))
        self.assertLessEqual(total_spend, D("20"))
        self.assertTrue(
            all(
                abs(d.applied_incentive - d.previous_incentive) <= D("1")
                for d in decisions
            )
        )
        self.assertTrue(all(d.applied_incentive <= D("5") for d in decisions))
        self.assertIn("budget_guard", {d.status for d in decisions})
        self.assertEqual(decisions[-1].applied_incentive, D("0"))

    def test_missing_and_stale_measurements_degrade_safely(self) -> None:
        decisions = replay_controller(
            config(),
            [
                LiquidityMeasurement(None),
                LiquidityMeasurement(D("8"), age_steps=2),
            ],
            initial_incentive=D("2"),
        )

        self.assertEqual([d.status for d in decisions], ["degraded", "degraded"])
        self.assertEqual(
            [d.applied_incentive for d in decisions],
            [D("1"), D("0")],
        )
        self.assertTrue(all(d.outside_streak == 0 for d in decisions))

    def test_replay_is_deterministic_and_auditable(self) -> None:
        measurements = (
            LiquidityMeasurement(D("8")),
            LiquidityMeasurement(D("8")),
            LiquidityMeasurement(D("11")),
            LiquidityMeasurement(None),
        )
        first = replay_controller(config(), measurements, initial_incentive=D("1"))
        second = replay_controller(config(), measurements, initial_incentive=D("1"))

        self.assertEqual(first, second)
        self.assertEqual([d.step for d in first], [1, 2, 3, 4])
        self.assertTrue(all(d.reason for d in first))
        self.assertTrue(all(d.budget_remaining >= 0 for d in first))

    def test_initial_state_rejects_budget_without_safe_ramp_reserve(self) -> None:
        with self.assertRaisesRegex(ValueError, "safely ramp down"):
            initial_state(config(budget="3"), initial_incentive=D("3"))


if __name__ == "__main__":
    unittest.main()
