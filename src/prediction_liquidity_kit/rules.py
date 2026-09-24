from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable, Mapping


class RuleError(ValueError):
    """Invalid, missing, ambiguous, or unsupported rule input."""


class RuleNotFound(RuleError):
    """No exact rule version/effective rule could be resolved."""


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RuleError(f"{name} is required and must be numeric")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise RuleError(f"{name} must be numeric") from exc
    if not result.is_finite():
        raise RuleError(f"{name} must be finite")
    return result


def _positive(value: object, name: str, *, allow_zero: bool = False) -> Decimal:
    result = _decimal(value, name)
    if result < 0 or (result == 0 and not allow_zero):
        op = "non-negative" if allow_zero else "positive"
        raise RuleError(f"{name} must be {op}")
    return result


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise RuleError("effective/replay timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _floor_cent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


@dataclass(frozen=True)
class RuleDefinition:
    venue: str
    program: str
    version: str
    family: str
    effective_from: datetime
    effective_to: datetime | None
    source_url: str
    source_snapshot_path: str
    source_snapshot_sha256: str
    notes: str

    def __post_init__(self) -> None:
        start = _utc(self.effective_from)
        end = _utc(self.effective_to) if self.effective_to is not None else None
        if end is not None and end <= start:
            raise RuleError("effective_to must be after effective_from")
        if len(self.source_snapshot_sha256) != 64:
            raise RuleError("source_snapshot_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "effective_from", start)
        object.__setattr__(self, "effective_to", end)

    def active_at(self, at: datetime) -> bool:
        moment = _utc(at)
        return self.effective_from <= moment and (
            self.effective_to is None or moment < self.effective_to
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "venue": self.venue,
            "program": self.program,
            "version": self.version,
            "family": self.family,
            "effective_from": self.effective_from.isoformat().replace("+00:00", "Z"),
            "effective_to": (
                self.effective_to.isoformat().replace("+00:00", "Z")
                if self.effective_to is not None
                else None
            ),
            "source_url": self.source_url,
            "source_snapshot_path": self.source_snapshot_path,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "notes": self.notes,
        }


def evaluate_kalshi_liquidity(inputs: Mapping[str, object]) -> dict[str, Decimal]:
    target_size = _positive(inputs.get("target_size"), "target_size")
    if not (Decimal("100") < target_size < Decimal("20000")):
        raise RuleError("target_size must satisfy 100 < target_size < 20000")

    discount = _positive(inputs.get("discount_factor"), "discount_factor")
    if discount > 1:
        raise RuleError("discount_factor must satisfy 0 < discount_factor <= 1")

    order_size = _positive(inputs.get("order_size"), "order_size")
    ticks_raw = inputs.get("ticks_away")
    if isinstance(ticks_raw, bool) or not isinstance(ticks_raw, int) or ticks_raw < 0:
        raise RuleError("ticks_away is required and must be a non-negative integer")

    user_period_score = _positive(
        inputs.get("user_period_score"), "user_period_score", allow_zero=True
    )
    all_period_score = _positive(inputs.get("all_period_score"), "all_period_score")
    if user_period_score > all_period_score:
        raise RuleError("user_period_score cannot exceed all_period_score")

    reward_pool = _positive(inputs.get("reward_pool"), "reward_pool", allow_zero=True)

    non_excluded = inputs.get("non_excluded_snapshots")
    total = inputs.get("total_snapshots")
    if isinstance(non_excluded, bool) or not isinstance(non_excluded, int) or non_excluded < 0:
        raise RuleError("non_excluded_snapshots must be a non-negative integer")
    if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
        raise RuleError("total_snapshots must be a positive integer")
    if non_excluded > total:
        raise RuleError("non_excluded_snapshots cannot exceed total_snapshots")

    raw_order_score = order_size * (discount ** ticks_raw)
    period_share = user_period_score / all_period_score
    coverage = Decimal(non_excluded) / Decimal(total)
    theoretical = _floor_cent(period_share * reward_pool * coverage)
    payable = theoretical if theoretical >= Decimal("1.00") else Decimal("0.00")
    return {
        "raw_order_score": raw_order_score,
        "period_share": period_share,
        "snapshot_coverage": coverage,
        "theoretical_reward": theoretical,
        "payable_reward": payable,
    }


def evaluate_kalshi_volume(inputs: Mapping[str, object]) -> dict[str, Decimal]:
    price = _decimal(inputs.get("contract_price"), "contract_price")
    if price < Decimal("0.03") or price > Decimal("0.97"):
        raise RuleError(
            "contract_price is outside the modeled eligible range 0.03..0.97; "
            "perpetual-futures exceptions are unsupported"
        )

    user_contracts = _positive(
        inputs.get("user_eligible_contracts"), "user_eligible_contracts", allow_zero=True
    )
    total_contracts = _positive(inputs.get("total_eligible_contracts"), "total_eligible_contracts")
    if user_contracts > total_contracts:
        raise RuleError("user_eligible_contracts cannot exceed total_eligible_contracts")
    reward_pool = _positive(inputs.get("reward_pool"), "reward_pool", allow_zero=True)

    share = user_contracts / total_contracts
    proportional = reward_pool * share
    cap = user_contracts * Decimal("0.005")
    reward = _floor_cent(min(proportional, cap))
    return {
        "volume_share": share,
        "proportional_reward": _floor_cent(proportional),
        "per_contract_cap_reward": _floor_cent(cap),
        "theoretical_reward": reward,
    }


_CALCULATORS: dict[str, Callable[[Mapping[str, object]], dict[str, Decimal]]] = {
    "kalshi_liquidity_v1": evaluate_kalshi_liquidity,
    "kalshi_volume_v1": evaluate_kalshi_volume,
}


class RuleRegistry:
    def __init__(self, rules: list[RuleDefinition] | None = None) -> None:
        self._rules: dict[str, RuleDefinition] = {}
        for rule in rules or []:
            self.add(rule)

    def add(self, rule: RuleDefinition) -> None:
        if rule.version in self._rules:
            raise RuleError(f"duplicate rule version: {rule.version}")
        if rule.family not in _CALCULATORS:
            raise RuleError(f"unsupported rule family: {rule.family}")
        self._rules[rule.version] = rule

    def list(self) -> list[RuleDefinition]:
        return sorted(
            self._rules.values(),
            key=lambda rule: (rule.venue, rule.program, rule.effective_from, rule.version),
        )

    def get(self, version: str) -> RuleDefinition:
        try:
            return self._rules[version]
        except KeyError as exc:
            raise RuleNotFound(f"unknown rule version: {version}") from exc

    def resolve(self, *, venue: str, program: str, at: datetime) -> RuleDefinition:
        matches = [
            rule
            for rule in self._rules.values()
            if rule.venue == venue and rule.program == program and rule.active_at(at)
        ]
        if not matches:
            raise RuleNotFound(f"no {venue}/{program} rule active at {_utc(at).isoformat()}")
        if len(matches) > 1:
            versions = ", ".join(sorted(rule.version for rule in matches))
            raise RuleError(f"ambiguous effective rules: {versions}")
        return matches[0]

    def evaluate(self, version: str, inputs: Mapping[str, object]) -> dict[str, object]:
        rule = self.get(version)
        values = _CALCULATORS[rule.family](inputs)
        return {
            "rule_version": rule.version,
            "family": rule.family,
            **{name: str(value) for name, value in values.items()},
        }


BUILTIN_RULES = [
    RuleDefinition(
        venue="kalshi",
        program="liquidity_incentive",
        version="kalshi-liquidity-help-2026-09-19",
        family="kalshi_liquidity_v1",
        effective_from=datetime(2026, 9, 19, tzinfo=timezone.utc),
        effective_to=datetime(2027, 1, 1, tzinfo=timezone.utc),
        source_url="https://help.kalshi.com/en/articles/13823851-liquidity-incentive-program",
        source_snapshot_path="docs/rule-snapshots/kalshi-liquidity-help-2026-09-19.json",
        source_snapshot_sha256="4bdcb317b7d8dc3232b70fe79eee72b47aef7660e94b923486ca5cc2ef468fcd",
        notes=(
            "Admitted from the public help terms retrieved 2026-09-19. "
            "The source states program end 2027-01-01 but not a start date, "
            "so this registry deliberately does not claim validity before admission."
        ),
    ),
    RuleDefinition(
        venue="kalshi",
        program="volume_incentive",
        version="kalshi-volume-help-2026-08-05",
        family="kalshi_volume_v1",
        effective_from=datetime(2026, 8, 5, tzinfo=timezone.utc),
        effective_to=datetime(2027, 9, 1, tzinfo=timezone.utc),
        source_url="https://help.kalshi.com/en/articles/13823850-what-is-the-kalshi-volume-incentive-program",
        source_snapshot_path="docs/rule-snapshots/kalshi-volume-help-2026-08-05.json",
        source_snapshot_sha256="7122d4e89f64c166766450c3fccabcab94dc666f673fa948ccb1e34a6f24bd51",
        notes=(
            "Public help article dated 2026-08-05. The calculator models the "
            "published 0.03..0.97 contract-price eligibility range and $0.005/contract cap; "
            "perpetual-futures exceptions are explicitly unsupported."
        ),
    ),
]


def builtin_registry() -> RuleRegistry:
    return RuleRegistry(list(BUILTIN_RULES))
