from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


_REQUIRED_ECONOMIC_FIELDS = (
    "theoretical_reward_rate",
    "expected_realized_reward_rate",
    "expected_spread_capture_rate",
    "expected_fill_rate",
    "fees_rate",
    "adverse_selection_rate",
    "inventory_risk_rate",
    "capital_cost_rate",
    "max_allocation",
    "risk_cap",
)


@dataclass(frozen=True)
class MarketEconomics:
    """Expected economics per unit of allocated capital.

    All monetary fields are rates per unit of capital. expected_fill_rate is
    a diagnostic assumption in [0, 1]; spread/fee/adverse-selection inputs
    must already be expressed as expected rates, so the fill assumption is
    surfaced without being silently multiplied twice.

    risk_cap is the maximum capital this market may receive under the caller's
    market-specific risk policy. None means UNKNOWN, not zero.
    """

    market_id: str
    theoretical_reward_rate: Decimal | None
    expected_realized_reward_rate: Decimal | None
    expected_spread_capture_rate: Decimal | None
    expected_fill_rate: Decimal | None
    fees_rate: Decimal | None
    adverse_selection_rate: Decimal | None
    inventory_risk_rate: Decimal | None
    capital_cost_rate: Decimal | None
    max_allocation: Decimal | None
    risk_cap: Decimal | None


@dataclass(frozen=True)
class EconomicDecomposition:
    theoretical_reward_rate: Decimal
    expected_realized_reward_rate: Decimal
    expected_spread_capture_rate: Decimal
    expected_fill_rate: Decimal
    fees_rate: Decimal
    adverse_selection_rate: Decimal
    inventory_risk_rate: Decimal
    capital_cost_rate: Decimal
    net_expected_rate: Decimal


@dataclass(frozen=True)
class EconomicValues:
    theoretical_reward: Decimal
    expected_realized_reward: Decimal
    expected_spread_capture: Decimal
    expected_filled_capital: Decimal
    fees: Decimal
    adverse_selection: Decimal
    inventory_risk_penalty: Decimal
    capital_cost: Decimal
    net_expected_value: Decimal


@dataclass(frozen=True)
class Allocation:
    market_id: str
    capital: Decimal
    decomposition: EconomicDecomposition
    values: EconomicValues


@dataclass(frozen=True)
class SkippedMarket:
    market_id: str
    reason: str


@dataclass(frozen=True)
class AllocationResult:
    capital_budget: Decimal
    allocated_capital: Decimal
    unallocated_capital: Decimal
    allocations: tuple[Allocation, ...]
    skipped: tuple[SkippedMarket, ...]


@dataclass(frozen=True)
class SensitivityPoint:
    market_id: str
    adverse_selection_multiplier: Decimal
    net_expected_rate: Decimal


def _missing_fields(market: MarketEconomics) -> tuple[str, ...]:
    return tuple(name for name in _REQUIRED_ECONOMIC_FIELDS if getattr(market, name) is None)


def _validate_market(market: MarketEconomics) -> None:
    if not market.market_id.strip():
        raise ValueError("market_id must be non-empty")

    missing = _missing_fields(market)
    if missing:
        return

    non_negative = (
        "theoretical_reward_rate",
        "expected_realized_reward_rate",
        "expected_spread_capture_rate",
        "fees_rate",
        "adverse_selection_rate",
        "inventory_risk_rate",
        "capital_cost_rate",
        "max_allocation",
        "risk_cap",
    )
    for name in non_negative:
        value = getattr(market, name)
        assert value is not None
        if value < 0:
            raise ValueError(f"{market.market_id}: {name} must be >= 0")

    fill = market.expected_fill_rate
    assert fill is not None
    if fill < 0 or fill > 1:
        raise ValueError(f"{market.market_id}: expected_fill_rate must be between 0 and 1")

    theoretical = market.theoretical_reward_rate
    realized = market.expected_realized_reward_rate
    assert theoretical is not None and realized is not None
    if realized > theoretical:
        raise ValueError(
            f"{market.market_id}: expected_realized_reward_rate cannot exceed theoretical_reward_rate"
        )


def decompose(market: MarketEconomics) -> EconomicDecomposition:
    """Return the explicit expected-rate decomposition for a fully known market."""

    _validate_market(market)
    missing = _missing_fields(market)
    if missing:
        raise ValueError(f"{market.market_id}: UNKNOWN fields: {', '.join(missing)}")

    theoretical = market.theoretical_reward_rate
    realized = market.expected_realized_reward_rate
    spread = market.expected_spread_capture_rate
    fill = market.expected_fill_rate
    fees = market.fees_rate
    adverse = market.adverse_selection_rate
    inventory = market.inventory_risk_rate
    capital_cost = market.capital_cost_rate
    assert None not in (theoretical, realized, spread, fill, fees, adverse, inventory, capital_cost)

    net = realized + spread - fees - adverse - inventory - capital_cost
    return EconomicDecomposition(
        theoretical_reward_rate=theoretical,
        expected_realized_reward_rate=realized,
        expected_spread_capture_rate=spread,
        expected_fill_rate=fill,
        fees_rate=fees,
        adverse_selection_rate=adverse,
        inventory_risk_rate=inventory,
        capital_cost_rate=capital_cost,
        net_expected_rate=net,
    )


def _scale(decomposition: EconomicDecomposition, capital: Decimal) -> EconomicValues:
    return EconomicValues(
        theoretical_reward=decomposition.theoretical_reward_rate * capital,
        expected_realized_reward=decomposition.expected_realized_reward_rate * capital,
        expected_spread_capture=decomposition.expected_spread_capture_rate * capital,
        expected_filled_capital=decomposition.expected_fill_rate * capital,
        fees=decomposition.fees_rate * capital,
        adverse_selection=decomposition.adverse_selection_rate * capital,
        inventory_risk_penalty=decomposition.inventory_risk_rate * capital,
        capital_cost=decomposition.capital_cost_rate * capital,
        net_expected_value=decomposition.net_expected_rate * capital,
    )


def allocate_capital(
    markets: Iterable[MarketEconomics],
    *,
    capital_budget: Decimal,
) -> AllocationResult:
    """Maximize linear expected net value under capital and per-market caps.

    This v1 optimizer is intentionally deterministic. Because the only global
    constraint is total capital and each eligible market has an independent
    notional/risk cap, sorting by expected net rate is the exact solution to
    this bounded linear allocation problem.
    """

    if capital_budget < 0:
        raise ValueError("capital_budget must be >= 0")

    market_list = list(markets)
    seen: set[str] = set()
    eligible: list[tuple[MarketEconomics, EconomicDecomposition, Decimal]] = []
    skipped: list[SkippedMarket] = []

    for market in market_list:
        if market.market_id in seen:
            raise ValueError(f"duplicate market_id: {market.market_id}")
        seen.add(market.market_id)

        _validate_market(market)
        missing = _missing_fields(market)
        if missing:
            skipped.append(
                SkippedMarket(
                    market_id=market.market_id,
                    reason="UNKNOWN:" + ",".join(missing),
                )
            )
            continue

        decomposition = decompose(market)
        max_allocation = market.max_allocation
        risk_cap = market.risk_cap
        assert max_allocation is not None and risk_cap is not None
        effective_cap = min(max_allocation, risk_cap)

        if effective_cap == 0:
            skipped.append(SkippedMarket(market.market_id, "ZERO_CAPACITY"))
            continue
        if decomposition.net_expected_rate <= 0:
            skipped.append(SkippedMarket(market.market_id, "NON_POSITIVE_NET_EXPECTED_RATE"))
            continue

        eligible.append((market, decomposition, effective_cap))

    eligible.sort(key=lambda item: (-item[1].net_expected_rate, item[0].market_id))

    remaining = capital_budget
    allocations: list[Allocation] = []
    for market, decomposition, effective_cap in eligible:
        if remaining == 0:
            break
        capital = min(remaining, effective_cap)
        if capital == 0:
            continue
        allocations.append(
            Allocation(
                market_id=market.market_id,
                capital=capital,
                decomposition=decomposition,
                values=_scale(decomposition, capital),
            )
        )
        remaining -= capital

    allocated = capital_budget - remaining
    return AllocationResult(
        capital_budget=capital_budget,
        allocated_capital=allocated,
        unallocated_capital=remaining,
        allocations=tuple(allocations),
        skipped=tuple(skipped),
    )


def adverse_selection_sensitivity(
    market: MarketEconomics,
    multipliers: Iterable[Decimal],
) -> tuple[SensitivityPoint, ...]:
    """Show net-rate sensitivity to the adverse-selection estimate."""

    baseline = decompose(market)
    points: list[SensitivityPoint] = []
    for multiplier in multipliers:
        if multiplier < 0:
            raise ValueError("adverse-selection multipliers must be >= 0")
        adjusted = (
            baseline.expected_realized_reward_rate
            + baseline.expected_spread_capture_rate
            - baseline.fees_rate
            - (baseline.adverse_selection_rate * multiplier)
            - baseline.inventory_risk_rate
            - baseline.capital_cost_rate
        )
        points.append(
            SensitivityPoint(
                market_id=market.market_id,
                adverse_selection_multiplier=multiplier,
                net_expected_rate=adjusted,
            )
        )
    return tuple(points)
