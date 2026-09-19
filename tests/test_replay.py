from __future__ import annotations

from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from prediction_liquidity_kit.replay import ReplayError, ReplayManifest, build_replay


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


if __name__ == "__main__":
    unittest.main()
