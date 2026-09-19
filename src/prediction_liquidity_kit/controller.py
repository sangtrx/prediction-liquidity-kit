from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Iterable


@dataclass(frozen=True)
class ControllerConfig:
    target_low: Decimal
    target_high: Decimal
    max_incentive: Decimal
    max_step_change: Decimal
    total_budget: Decimal
    confirmation_steps: int = 2
    stale_after_steps: int = 1

    def __post_init__(self) -> None:
        decimals = {
            "target_low": self.target_low,
            "target_high": self.target_high,
            "max_incentive": self.max_incentive,
            "max_step_change": self.max_step_change,
            "total_budget": self.total_budget,
        }
        for name, value in decimals.items():
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.target_low > self.target_high:
            raise ValueError("target_low must not exceed target_high")
        if self.max_step_change <= 0:
            raise ValueError("max_step_change must be positive")
        if self.confirmation_steps < 1:
            raise ValueError("confirmation_steps must be positive")
        if self.stale_after_steps < 0:
            raise ValueError("stale_after_steps must be non-negative")


@dataclass(frozen=True)
class LiquidityMeasurement:
    value: Decimal | None
    age_steps: int = 0

    def __post_init__(self) -> None:
        if self.value is not None:
            if not self.value.is_finite() or self.value < 0:
                raise ValueError("measurement value must be finite and non-negative")
        if self.age_steps < 0:
            raise ValueError("age_steps must be non-negative")


@dataclass(frozen=True)
class ControllerState:
    step: int
    current_incentive: Decimal
    spent: Decimal
    outside_direction: str | None = None
    outside_streak: int = 0


@dataclass(frozen=True)
class ControllerDecision:
    step: int
    measurement_value: Decimal | None
    measurement_age_steps: int
    status: str
    previous_incentive: Decimal
    requested_incentive: Decimal
    applied_incentive: Decimal
    spend: Decimal
    budget_remaining: Decimal
    outside_direction: str | None
    outside_streak: int
    reason: str


def _ramp_reserve(level: Decimal, max_step_change: Decimal) -> Decimal:
    """Minimum future spend needed to ramp a positive level down within the step cap."""
    if level <= 0:
        return Decimal("0")
    positive_future_steps = int(
        (level / max_step_change).to_integral_value(rounding=ROUND_CEILING)
    ) - 1
    if positive_future_steps <= 0:
        return Decimal("0")
    n = Decimal(positive_future_steps)
    return n * level - max_step_change * n * (n + Decimal("1")) / Decimal("2")


def _required_budget(level: Decimal, max_step_change: Decimal) -> Decimal:
    return level + _ramp_reserve(level, max_step_change)


def initial_state(
    config: ControllerConfig,
    *,
    initial_incentive: Decimal = Decimal("0"),
) -> ControllerState:
    if not initial_incentive.is_finite() or initial_incentive < 0:
        raise ValueError("initial_incentive must be finite and non-negative")
    if initial_incentive > config.max_incentive:
        raise ValueError("initial_incentive exceeds max_incentive")
    if _required_budget(initial_incentive, config.max_step_change) > config.total_budget:
        raise ValueError("initial incentive cannot safely ramp down within total_budget")
    return ControllerState(
        step=0,
        current_incentive=initial_incentive,
        spent=Decimal("0"),
    )


def _measurement_direction(
    config: ControllerConfig,
    measurement: LiquidityMeasurement,
) -> tuple[str | None, str | None]:
    if measurement.value is None:
        return None, "measurement missing"
    if measurement.age_steps > config.stale_after_steps:
        return None, "measurement stale"
    if measurement.value < config.target_low:
        return "below", None
    if measurement.value > config.target_high:
        return "above", None
    return None, None


def controller_step(
    config: ControllerConfig,
    state: ControllerState,
    measurement: LiquidityMeasurement,
) -> tuple[ControllerState, ControllerDecision]:
    if state.step < 0 or state.spent < 0:
        raise ValueError("controller state is invalid")
    if state.current_incentive < 0 or state.current_incentive > config.max_incentive:
        raise ValueError("controller state incentive is outside configured bounds")
    if state.spent > config.total_budget:
        raise ValueError("controller state exceeds total budget")

    previous = state.current_incentive
    remaining_before = config.total_budget - state.spent
    direction, degraded_reason = _measurement_direction(config, measurement)

    if degraded_reason is not None:
        next_direction = None
        next_streak = 0
        requested = max(Decimal("0"), previous - config.max_step_change)
        status = "degraded"
        reason = f"{degraded_reason}; degrading incentive toward zero"
    else:
        if direction is None:
            next_direction = None
            next_streak = 0
            requested = previous
            status = "ok"
            reason = "measurement within target band; hold inside deadband"
        else:
            if state.outside_direction == direction:
                next_streak = state.outside_streak + 1
            else:
                next_streak = 1
            next_direction = direction

            if next_streak < config.confirmation_steps:
                requested = previous
                status = "ok"
                reason = f"{direction} target; waiting for hysteresis confirmation"
            elif direction == "below":
                requested = min(
                    config.max_incentive,
                    previous + config.max_step_change,
                )
                status = "ok"
                reason = "confirmed below target; increase incentive within step cap"
            else:
                requested = max(
                    Decimal("0"),
                    previous - config.max_step_change,
                )
                status = "ok"
                reason = "confirmed above target; decrease incentive within step cap"

    requested = min(config.max_incentive, max(Decimal("0"), requested))
    if abs(requested - previous) > config.max_step_change:
        raise RuntimeError("requested action violates max_step_change")

    applied = requested
    if _required_budget(applied, config.max_step_change) > remaining_before:
        safe = max(Decimal("0"), previous - config.max_step_change)
        if _required_budget(safe, config.max_step_change) > remaining_before:
            raise RuntimeError("budget-ramp invariant violated")
        applied = safe
        if status == "degraded":
            reason += "; budget guard forced the safest legal ramp-down"
        else:
            status = "budget_guard"
            reason = "budget guard forced a legal ramp-down with reserve for future capped steps"

    if abs(applied - previous) > config.max_step_change:
        raise RuntimeError("applied action violates max_step_change")
    if applied > remaining_before:
        raise RuntimeError("applied action exceeds remaining budget")

    spend = applied
    spent = state.spent + spend
    remaining_after = config.total_budget - spent
    if spent > config.total_budget:
        raise RuntimeError("controller exceeded total budget")

    next_state = ControllerState(
        step=state.step + 1,
        current_incentive=applied,
        spent=spent,
        outside_direction=next_direction,
        outside_streak=next_streak,
    )
    decision = ControllerDecision(
        step=next_state.step,
        measurement_value=measurement.value,
        measurement_age_steps=measurement.age_steps,
        status=status,
        previous_incentive=previous,
        requested_incentive=requested,
        applied_incentive=applied,
        spend=spend,
        budget_remaining=remaining_after,
        outside_direction=next_direction,
        outside_streak=next_streak,
        reason=reason,
    )
    return next_state, decision


def replay_controller(
    config: ControllerConfig,
    measurements: Iterable[LiquidityMeasurement],
    *,
    initial_incentive: Decimal = Decimal("0"),
) -> tuple[ControllerDecision, ...]:
    state = initial_state(config, initial_incentive=initial_incentive)
    decisions: list[ControllerDecision] = []
    for measurement in measurements:
        state, decision = controller_step(config, state, measurement)
        decisions.append(decision)
    return tuple(decisions)
