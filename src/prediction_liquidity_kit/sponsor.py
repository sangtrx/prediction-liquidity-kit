from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


MIN_CALIBRATION_SAMPLES = 10


@dataclass(frozen=True)
class LiquidityTarget:
    max_spread_bps: Decimal
    min_depth: Decimal
    min_quote_uptime: Decimal

    def __post_init__(self) -> None:
        if self.max_spread_bps < 0 or self.min_depth < 0:
            raise ValueError("liquidity targets must be non-negative")
        if not Decimal("0") <= self.min_quote_uptime <= Decimal("1"):
            raise ValueError("min_quote_uptime must be in [0, 1]")


@dataclass(frozen=True)
class ResponsePoint:
    reward_per_period: Decimal
    spread_bps: Decimal
    depth: Decimal
    quote_uptime: Decimal

    def __post_init__(self) -> None:
        if self.reward_per_period < 0 or self.spread_bps < 0 or self.depth < 0:
            raise ValueError("response point values must be non-negative")
        if not Decimal("0") <= self.quote_uptime <= Decimal("1"):
            raise ValueError("quote_uptime must be in [0, 1]")


@dataclass(frozen=True)
class Calibration:
    points: tuple[ResponsePoint, ...]
    sample_size: int
    uncertainty_fraction: Decimal
    evidence_kind: str = "synthetic"
    causal_evidence: bool = False

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("calibration requires at least two response points")
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")
        if not Decimal("0") <= self.uncertainty_fraction < Decimal("1"):
            raise ValueError("uncertainty_fraction must be in [0, 1)")
        if self.evidence_kind not in {"synthetic", "observed"}:
            raise ValueError("evidence_kind must be 'synthetic' or 'observed'")
        rewards = [point.reward_per_period for point in sorted(self.points, key=lambda p: p.reward_per_period)]
        if len(set(rewards)) != len(rewards):
            raise ValueError("reward_per_period values must be unique")


@dataclass(frozen=True)
class MarketBudgetRequest:
    market_id: str
    target: LiquidityTarget
    calibration: Calibration
    current_reward_per_period: Decimal
    max_reward_per_period: Decimal
    max_rate_change_per_period: Decimal
    periods: int = 1

    def __post_init__(self) -> None:
        if not self.market_id.strip():
            raise ValueError("market_id is required")
        if self.current_reward_per_period < 0 or self.max_reward_per_period < 0:
            raise ValueError("reward values must be non-negative")
        if self.max_rate_change_per_period < 0:
            raise ValueError("max_rate_change_per_period must be non-negative")
        if self.periods < 1:
            raise ValueError("periods must be positive")


@dataclass(frozen=True)
class LiquidityEstimate:
    spread_bps: Decimal
    depth: Decimal
    quote_uptime: Decimal


@dataclass(frozen=True)
class UncertaintyBounds:
    spread_bps_lower: Decimal
    spread_bps_upper: Decimal
    depth_lower: Decimal
    depth_upper: Decimal
    quote_uptime_lower: Decimal
    quote_uptime_upper: Decimal


@dataclass(frozen=True)
class SensitivityRow:
    reward_per_period: Decimal
    estimate: LiquidityEstimate
    bounds: UncertaintyBounds
    conservative_target_met: bool


@dataclass(frozen=True)
class MarketBudgetDecision:
    market_id: str
    reward_per_period: Decimal
    periods: int
    expected_spend: Decimal
    estimate: LiquidityEstimate
    bounds: UncertaintyBounds
    sensitivity: tuple[SensitivityRow, ...]
    evidence_kind: str
    qualification: str


@dataclass(frozen=True)
class SponsorBudgetPlan:
    status: str
    total_budget: Decimal
    expected_spend: Decimal
    decisions: tuple[MarketBudgetDecision, ...]
    reason: str | None = None


def _sorted_points(calibration: Calibration) -> tuple[ResponsePoint, ...]:
    return tuple(sorted(calibration.points, key=lambda point: point.reward_per_period))


def interpolate_response(calibration: Calibration, reward_per_period: Decimal) -> LiquidityEstimate:
    points = _sorted_points(calibration)
    if reward_per_period < points[0].reward_per_period or reward_per_period > points[-1].reward_per_period:
        raise ValueError("reward is outside the calibrated range")

    for point in points:
        if reward_per_period == point.reward_per_period:
            return LiquidityEstimate(point.spread_bps, point.depth, point.quote_uptime)

    for left, right in zip(points, points[1:]):
        if left.reward_per_period < reward_per_period < right.reward_per_period:
            width = right.reward_per_period - left.reward_per_period
            fraction = (reward_per_period - left.reward_per_period) / width
            return LiquidityEstimate(
                spread_bps=left.spread_bps + fraction * (right.spread_bps - left.spread_bps),
                depth=left.depth + fraction * (right.depth - left.depth),
                quote_uptime=left.quote_uptime + fraction * (right.quote_uptime - left.quote_uptime),
            )
    raise ValueError("reward could not be interpolated")


def uncertainty_bounds(estimate: LiquidityEstimate, uncertainty_fraction: Decimal) -> UncertaintyBounds:
    lower_factor = Decimal("1") - uncertainty_fraction
    upper_factor = Decimal("1") + uncertainty_fraction
    return UncertaintyBounds(
        spread_bps_lower=max(Decimal("0"), estimate.spread_bps * lower_factor),
        spread_bps_upper=estimate.spread_bps * upper_factor,
        depth_lower=max(Decimal("0"), estimate.depth * lower_factor),
        depth_upper=estimate.depth * upper_factor,
        quote_uptime_lower=max(Decimal("0"), estimate.quote_uptime * lower_factor),
        quote_uptime_upper=min(Decimal("1"), estimate.quote_uptime * upper_factor),
    )


def conservative_target_met(bounds: UncertaintyBounds, target: LiquidityTarget) -> bool:
    return (
        bounds.spread_bps_upper <= target.max_spread_bps
        and bounds.depth_lower >= target.min_depth
        and bounds.quote_uptime_lower >= target.min_quote_uptime
    )


def _crossing_reward(
    left_reward: Decimal,
    right_reward: Decimal,
    left_value: Decimal,
    right_value: Decimal,
    target_value: Decimal,
) -> Decimal | None:
    if left_value == right_value:
        return None
    low = min(left_value, right_value)
    high = max(left_value, right_value)
    if target_value < low or target_value > high:
        return None
    fraction = (target_value - left_value) / (right_value - left_value)
    return left_reward + fraction * (right_reward - left_reward)


def _candidate_rewards(request: MarketBudgetRequest) -> tuple[Decimal, ...]:
    calibration = request.calibration
    points = _sorted_points(calibration)
    uncertainty = calibration.uncertainty_fraction
    candidates = {point.reward_per_period for point in points}

    spread_threshold = request.target.max_spread_bps / (Decimal("1") + uncertainty)
    depth_threshold = request.target.min_depth / (Decimal("1") - uncertainty)
    uptime_threshold = request.target.min_quote_uptime / (Decimal("1") - uncertainty)

    for left, right in zip(points, points[1:]):
        for left_value, right_value, target_value in (
            (left.spread_bps, right.spread_bps, spread_threshold),
            (left.depth, right.depth, depth_threshold),
            (left.quote_uptime, right.quote_uptime, uptime_threshold),
        ):
            crossing = _crossing_reward(
                left.reward_per_period,
                right.reward_per_period,
                left_value,
                right_value,
                target_value,
            )
            if crossing is not None:
                candidates.add(crossing)

    return tuple(sorted(candidates))


def sensitivity_table(request: MarketBudgetRequest) -> tuple[SensitivityRow, ...]:
    rows: list[SensitivityRow] = []
    for reward in _candidate_rewards(request):
        estimate = interpolate_response(request.calibration, reward)
        bounds = uncertainty_bounds(estimate, request.calibration.uncertainty_fraction)
        rows.append(
            SensitivityRow(
                reward_per_period=reward,
                estimate=estimate,
                bounds=bounds,
                conservative_target_met=conservative_target_met(bounds, request.target),
            )
        )
    return tuple(rows)


def _qualification(calibration: Calibration, exploratory: bool) -> str:
    if exploratory and calibration.sample_size < MIN_CALIBRATION_SAMPLES:
        return "exploratory only: sparse calibration; uncertainty may be understated"
    if calibration.causal_evidence:
        return "calibrated response; causal interpretation depends on the stated evidence design"
    return "association-only response calibration; do not interpret as causal elasticity"


def _choose_market_decision(
    request: MarketBudgetRequest,
    *,
    exploratory: bool,
) -> MarketBudgetDecision | None:
    allowed_min = max(
        Decimal("0"),
        request.current_reward_per_period - request.max_rate_change_per_period,
    )
    allowed_max = min(
        request.max_reward_per_period,
        request.current_reward_per_period + request.max_rate_change_per_period,
    )

    rows = list(sensitivity_table(request))
    calibrated_rewards = tuple(
        point.reward_per_period for point in _sorted_points(request.calibration)
    )
    if allowed_min <= allowed_max:
        for reward in (allowed_min, allowed_max):
            if (
                calibrated_rewards[0] <= reward <= calibrated_rewards[-1]
                and all(row.reward_per_period != reward for row in rows)
            ):
                estimate = interpolate_response(request.calibration, reward)
                bounds = uncertainty_bounds(
                    estimate,
                    request.calibration.uncertainty_fraction,
                )
                rows.append(
                    SensitivityRow(
                        reward_per_period=reward,
                        estimate=estimate,
                        bounds=bounds,
                        conservative_target_met=conservative_target_met(
                            bounds,
                            request.target,
                        ),
                    )
                )
    rows.sort(key=lambda row: row.reward_per_period)
    sensitivity = tuple(rows)

    for row in sensitivity:
        if row.reward_per_period < allowed_min or row.reward_per_period > allowed_max:
            continue
        if row.conservative_target_met:
            return MarketBudgetDecision(
                market_id=request.market_id,
                reward_per_period=row.reward_per_period,
                periods=request.periods,
                expected_spend=row.reward_per_period * request.periods,
                estimate=row.estimate,
                bounds=row.bounds,
                sensitivity=sensitivity,
                evidence_kind=request.calibration.evidence_kind,
                qualification=_qualification(request.calibration, exploratory),
            )
    return None


def optimize_sponsor_budget(
    requests: Iterable[MarketBudgetRequest],
    *,
    total_budget: Decimal,
    exploratory: bool = False,
) -> SponsorBudgetPlan:
    if total_budget < 0:
        raise ValueError("total_budget must be non-negative")

    ordered = tuple(sorted(requests, key=lambda request: request.market_id))
    if not ordered:
        return SponsorBudgetPlan(
            status="no_decision",
            total_budget=total_budget,
            expected_spend=Decimal("0"),
            decisions=(),
            reason="no markets supplied",
        )

    if not exploratory:
        sparse = [
            request.market_id
            for request in ordered
            if request.calibration.sample_size < MIN_CALIBRATION_SAMPLES
        ]
        if sparse:
            return SponsorBudgetPlan(
                status="no_decision",
                total_budget=total_budget,
                expected_spend=Decimal("0"),
                decisions=(),
                reason=f"insufficient calibration for: {', '.join(sparse)}",
            )

    decisions: list[MarketBudgetDecision] = []
    for request in ordered:
        decision = _choose_market_decision(request, exploratory=exploratory)
        if decision is None:
            return SponsorBudgetPlan(
                status="no_decision",
                total_budget=total_budget,
                expected_spend=Decimal("0"),
                decisions=(),
                reason=f"target infeasible within calibrated reward/rate caps for {request.market_id}",
            )
        decisions.append(decision)

    expected_spend = sum((decision.expected_spend for decision in decisions), Decimal("0"))
    if expected_spend > total_budget:
        return SponsorBudgetPlan(
            status="no_decision",
            total_budget=total_budget,
            expected_spend=Decimal("0"),
            decisions=(),
            reason="hard sponsor budget would be exceeded",
        )

    status = (
        "exploratory"
        if exploratory and any(
            request.calibration.sample_size < MIN_CALIBRATION_SAMPLES for request in ordered
        )
        else "ok"
    )
    return SponsorBudgetPlan(
        status=status,
        total_budget=total_budget,
        expected_spend=expected_spend,
        decisions=tuple(decisions),
    )
