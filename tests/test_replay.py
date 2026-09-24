from __future__ import annotations

from pathlib import Path
from decimal import Decimal as D
import hashlib
import json
import tempfile
import unittest

from prediction_liquidity_kit.replay import (
    ReplayError,
    ReplayManifest,
    build_replay,
    run_economic_replay,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "replay"
    / "kalshi-volume-synthetic-v1"
    / "manifest.json"
)


class ReplayFixtureTest(unittest.TestCase):
    def test_same_manifest_rebuilds_identical_normalized_hash(self) -> None:
        first = build_replay(FIXTURE)
        second = build_replay(FIXTURE)
        manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.sha256, manifest["normalized_fixture_sha256"])

    def test_future_rule_version_cannot_leak_backward(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["rule"]["effective_from"] = "2026-09-20T00:00:00Z"

        with self.assertRaisesRegex(ReplayError, "outside the bound rule-version"):
            ReplayManifest.from_mapping(payload)

    def test_observation_timestamp_must_stay_within_manifest_window(self) -> None:
        root = FIXTURE.parent
        manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
        observations = json.loads((root / "observations.json").read_text(encoding="utf-8"))
        observations["observations"][0]["timestamp"] = manifest["window"]["end"]

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            broken = target / "observations.json"
            broken.write_text(json.dumps(observations, sort_keys=True), encoding="utf-8")
            manifest["files"][0]["sha256"] = hashlib.sha256(broken.read_bytes()).hexdigest()
            manifest["normalized_fixture_sha256"] = "0" * 64
            (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ReplayError, "outside the replay window"):
                build_replay(target / "manifest.json")

    def test_tagged_fields_require_classification(self) -> None:
        root = FIXTURE.parent
        manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
        observations = json.loads((root / "observations.json").read_text(encoding="utf-8"))
        observations["observations"][0]["economics"]["fees_rate"].pop("classification")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            broken = target / "observations.json"
            broken.write_text(json.dumps(observations, sort_keys=True), encoding="utf-8")
            manifest["files"][0]["sha256"] = hashlib.sha256(broken.read_bytes()).hexdigest()
            manifest["normalized_fixture_sha256"] = "0" * 64
            (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ReplayError, "requires both value and classification"):
                build_replay(target / "manifest.json")

    def test_fixture_explicitly_forbids_profitability_claim(self) -> None:
        manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertFalse(manifest["profitability_claim_allowed"])
        self.assertTrue(manifest["gaps"])
        self.assertTrue(manifest["survivorship_caveats"])


    def test_synthetic_fixture_drives_reward_rule_and_mm_allocator(self) -> None:
        result = run_economic_replay(FIXTURE, capital_budget=D("50"))
        manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(result.replay_sha256, manifest["normalized_fixture_sha256"])
        self.assertEqual(result.rule_output["rule_version"], "kalshi-volume-help-2026-08-05")
        self.assertEqual(result.rule_output["theoretical_reward"], "5.00")
        self.assertEqual(result.allocation.allocated_capital, D("50"))
        self.assertEqual(result.allocation.unallocated_capital, D("0"))
        self.assertEqual(len(result.allocation.allocations), 1)
        allocation = result.allocation.allocations[0]
        self.assertEqual(allocation.decomposition.theoretical_reward_rate, D("0.05"))
        self.assertEqual(allocation.decomposition.net_expected_rate, D("0.041"))
        self.assertEqual(allocation.values.net_expected_value, D("2.050"))


if __name__ == "__main__":
    unittest.main()
