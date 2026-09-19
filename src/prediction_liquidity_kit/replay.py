from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Mapping


class ReplayError(ValueError):
    """Invalid or non-reproducible replay input."""


_ALLOWED_CLASSIFICATIONS = frozenset({"observed", "estimated", "synthetic", "unknown"})


def _utc(value: str, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ReplayError(f"{name} must be a non-empty timestamp")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ReplayError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ReplayError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ReplayError("fixture must be canonical JSON data") from exc
    return rendered.encode("utf-8")


def _validate_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ReplayError(f"{name} must be a SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ReplayError(f"{name} must be a SHA-256 hex digest") from exc
    return value.lower()


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayError(f"{name} must be non-empty")
    return value.strip()


@dataclass(frozen=True)
class ReplayInput:
    path: str
    sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ReplayInput":
        path = _require_text(value.get("path"), "files[].path")
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ReplayError("files[].path must stay within the replay directory")
        return cls(path=path, sha256=_validate_digest(value.get("sha256"), "files[].sha256"))


@dataclass(frozen=True)
class ReplayManifest:
    schema_version: int
    dataset_id: str
    venue: str
    market_id: str
    source_revision: str
    window_start: datetime
    window_end: datetime
    rule_version: str
    rule_effective_from: datetime
    rule_effective_to: datetime | None
    files: tuple[ReplayInput, ...]
    gaps: tuple[str, ...]
    survivorship_caveats: tuple[str, ...]
    profitability_claim_allowed: bool
    normalized_fixture_sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ReplayManifest":
        if value.get("schema_version") != 1:
            raise ReplayError("schema_version must be 1")

        window = value.get("window")
        rule = value.get("rule")
        raw_files = value.get("files")
        if not isinstance(window, Mapping) or not isinstance(rule, Mapping):
            raise ReplayError("window and rule must be objects")
        if not isinstance(raw_files, list) or not raw_files:
            raise ReplayError("files must be a non-empty list")

        start = _utc(window.get("start"), "window.start")  # type: ignore[arg-type]
        end = _utc(window.get("end"), "window.end")  # type: ignore[arg-type]
        if end <= start:
            raise ReplayError("window.end must be after window.start")

        rule_start = _utc(rule.get("effective_from"), "rule.effective_from")  # type: ignore[arg-type]
        raw_rule_end = rule.get("effective_to")
        rule_end = None if raw_rule_end is None else _utc(raw_rule_end, "rule.effective_to")  # type: ignore[arg-type]
        if rule_end is not None and rule_end <= rule_start:
            raise ReplayError("rule.effective_to must be after rule.effective_from")
        if start < rule_start or (rule_end is not None and end > rule_end):
            raise ReplayError("replay window is outside the bound rule-version effective window")

        files = tuple(ReplayInput.from_mapping(item) for item in raw_files if isinstance(item, Mapping))
        if len(files) != len(raw_files):
            raise ReplayError("files entries must be objects")
        if len({item.path for item in files}) != len(files):
            raise ReplayError("files paths must be unique")

        gaps = value.get("gaps")
        caveats = value.get("survivorship_caveats")
        if not isinstance(gaps, list) or not all(isinstance(item, str) and item.strip() for item in gaps):
            raise ReplayError("gaps must be an explicit list of non-empty strings")
        if not isinstance(caveats, list) or not all(isinstance(item, str) and item.strip() for item in caveats):
            raise ReplayError("survivorship_caveats must be an explicit list of non-empty strings")

        if value.get("profitability_claim_allowed") is not False:
            raise ReplayError("v1 replay manifests must set profitability_claim_allowed=false")

        return cls(
            schema_version=1,
            dataset_id=_require_text(value.get("dataset_id"), "dataset_id"),
            venue=_require_text(value.get("venue"), "venue"),
            market_id=_require_text(value.get("market_id"), "market_id"),
            source_revision=_require_text(value.get("source_revision"), "source_revision"),
            window_start=start,
            window_end=end,
            rule_version=_require_text(rule.get("version"), "rule.version"),
            rule_effective_from=rule_start,
            rule_effective_to=rule_end,
            files=files,
            gaps=tuple(item.strip() for item in gaps),
            survivorship_caveats=tuple(item.strip() for item in caveats),
            profitability_claim_allowed=False,
            normalized_fixture_sha256=_validate_digest(
                value.get("normalized_fixture_sha256"),
                "normalized_fixture_sha256",
            ),
        )


@dataclass(frozen=True)
class ReplayBuild:
    normalized: Mapping[str, object]
    sha256: str


def _validate_classifications(value: object, path: str = "$") -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_classifications(item, f"{path}[{index}]")
        return
    if not isinstance(value, dict):
        return

    has_value = "value" in value
    has_classification = "classification" in value
    if has_value != has_classification:
        raise ReplayError(f"{path}: tagged field requires both value and classification")
    if has_value and value["classification"] not in _ALLOWED_CLASSIFICATIONS:
        raise ReplayError(f"{path}.classification is unsupported")

    for key, item in value.items():
        _validate_classifications(item, f"{path}.{key}")


def load_manifest(path: str | Path) -> ReplayManifest:
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"cannot read replay manifest: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise ReplayError("manifest root must be an object")
    return ReplayManifest.from_mapping(payload)


def build_replay(path: str | Path) -> ReplayBuild:
    manifest_path = Path(path)
    manifest = load_manifest(manifest_path)
    root = manifest_path.parent

    normalized_files: list[dict[str, object]] = []
    for item in sorted(manifest.files, key=lambda record: record.path):
        input_path = root / item.path
        try:
            raw = input_path.read_bytes()
        except OSError as exc:
            raise ReplayError(f"cannot read replay input: {item.path}") from exc
        if _sha256(raw) != item.sha256:
            raise ReplayError(f"{item.path}: SHA-256 mismatch")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReplayError(f"{item.path}: replay input must be UTF-8 JSON") from exc
        _validate_classifications(payload, f"$.files[{item.path}]")
        normalized_files.append({"path": item.path, "sha256": item.sha256, "payload": payload})

    normalized: dict[str, object] = {
        "schema_version": manifest.schema_version,
        "dataset_id": manifest.dataset_id,
        "venue": manifest.venue,
        "market_id": manifest.market_id,
        "source_revision": manifest.source_revision,
        "window": {
            "start": manifest.window_start.isoformat().replace("+00:00", "Z"),
            "end": manifest.window_end.isoformat().replace("+00:00", "Z"),
        },
        "rule": {
            "version": manifest.rule_version,
            "effective_from": manifest.rule_effective_from.isoformat().replace("+00:00", "Z"),
            "effective_to": (
                manifest.rule_effective_to.isoformat().replace("+00:00", "Z")
                if manifest.rule_effective_to is not None
                else None
            ),
        },
        "gaps": list(manifest.gaps),
        "survivorship_caveats": list(manifest.survivorship_caveats),
        "profitability_claim_allowed": False,
        "files": normalized_files,
    }
    digest = _sha256(_canonical_bytes(normalized))
    if digest != manifest.normalized_fixture_sha256:
        raise ReplayError("normalized replay fixture SHA-256 mismatch")
    return ReplayBuild(normalized=normalized, sha256=digest)
