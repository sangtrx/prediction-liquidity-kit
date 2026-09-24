from __future__ import annotations

from decimal import Decimal as D
import json
from pathlib import Path

from prediction_liquidity_kit.allocator import MarketEconomics, allocate_capital
from prediction_liquidity_kit.replay import build_replay
from prediction_liquidity_kit.rules import builtin_registry
from prediction_liquidity_kit.sponsor import (
    Calibration,
    LiquidityTarget,
    MarketBudgetRequest,
    ResponsePoint,
    optimize_sponsor_budget,
)


def main() -> None:
    """Run deterministic, non-live public examples with explicit evidence classes."""
    rule = builtin_registry().evaluate(
        "kalshi-volume-help-2026-08-05",
        {
            "contract_price": "0.50",
            "user_eligible_contracts": "1000",
            "total_eligible_contracts": "10000",
            "reward_pool": "100",
        },
    )

    allocation = allocate_capital(
        [
            MarketEconomics(
                market_id="synthetic-market-a",
                theoretical_reward_rate=D("0.08"),
                expected_realized_reward_rate=D("0.05"),
                expected_spread_capture_rate=D("0.02"),
                expected_fill_rate=D("0.50"),
                fees_rate=D("0.01"),
                adverse_selection_rate=D("0.01"),
                inventory_risk_rate=D("0.003"),
                capital_cost_rate=D("0.002"),
                max_allocation=D("100"),
                risk_cap=D("30"),
            )
        ],
        capital_budget=D("50"),
    )

    sponsor = optimize_sponsor_budget(
        [
            MarketBudgetRequest(
                market_id="synthetic-market-a",
                target=LiquidityTarget(
                    max_spread_bps=D("13.2"),
                    min_depth=D("135"),
                    min_quote_uptime=D("0.81"),
                ),
                calibration=Calibration(
                    points=(
                        ResponsePoint(D("0"), D("20"), D("100"), D("0.80")),
                        ResponsePoint(D("10"), D("10"), D("200"), D("0.95")),
                    ),
                    sample_size=20,
                    uncertainty_fraction=D("0.10"),
                    evidence_kind="synthetic",
                ),
                current_reward_per_period=D("5"),
                max_reward_per_period=D("10"),
                max_rate_change_per_period=D("5"),
                periods=2,
            )
        ],
        total_budget=D("20"),
    )

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "replay"
        / "kalshi-volume-synthetic-v1"
        / "manifest.json"
    )
    replay = build_replay(fixture)

    output = {
        "boundary": "simulation-only; no credentials, orders, capital, or sponsor funds are mutated",
        "evidence": {
            "rule_inputs": "synthetic",
            "allocation_economics": "estimated+synthetic",
            "sponsor_calibration": "synthetic",
            "replay_fixture": "synthetic",
        },
        "reward_rule": rule,
        "capital_allocation": {
            "allocated_capital": str(allocation.allocated_capital),
            "unallocated_capital": str(allocation.unallocated_capital),
            "allocations": [
                {
                    "market_id": item.market_id,
                    "capital": str(item.capital),
                    "net_expected_rate": str(item.decomposition.net_expected_rate),
                }
                for item in allocation.allocations
            ],
        },
        "sponsor_simulation": {
            "status": sponsor.status,
            "expected_spend": str(sponsor.expected_spend),
            "decisions": [
                {
                    "market_id": item.market_id,
                    "reward_per_period": str(item.reward_per_period),
                    "qualification": item.qualification,
                }
                for item in sponsor.decisions
            ],
        },
        "replay": {"sha256": replay.sha256, "profitability_claim_allowed": False},
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
