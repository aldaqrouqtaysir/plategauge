from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_release_gate import ReleaseGateError, main, verify_release_gate

TAG = "v1.0.0"
COMMIT = "a" * 40


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_release(root: Path) -> Path:
    model_path = root / "web/public/models/plategauge.onnx"
    manifest_path = root / "web/public/models/release.json"
    results_path = root / "reports/results.json"
    claim_path = root / "docs/CLAIM_EVIDENCE_MAP.csv"
    approval_path = root / "release/gate-d-approval.json"
    for path in (model_path, manifest_path, results_path, claim_path, approval_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"frozen-model")
    manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "modelVersion": TAG,
                "modelPath": "models/plategauge.onnx",
                "modelSha256": digest(model_path),
                "beforeInputName": "before",
                "afterInputName": "after",
                "outputName": "quantiles",
                "calibration": {
                    "lowerExpansion": 0.02,
                    "upperExpansion": 0.02,
                    "abstentionWidth": 0.30,
                    "intervalGatePassed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    results_path.write_text(json.dumps({"schemaVersion": 1, "frozen": True}), encoding="utf-8")
    claim_path.write_text("claim_id,status\nC001,SUPPORTED\n", encoding="utf-8")
    approval_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "gate": "D",
                "decision": "approved",
                "approvedBy": "Taysir Al Daqrouq",
                "approvedAt": "2026-10-20T12:00:00+04:00",
                "releaseTag": TAG,
                "sourceCommitSha": COMMIT,
                "evidence": {
                    "modelSha256": digest(model_path),
                    "releaseManifestSha256": digest(manifest_path),
                    "resultsSha256": digest(results_path),
                    "claimEvidenceSha256": digest(claim_path),
                },
            }
        ),
        encoding="utf-8",
    )
    return approval_path


class ReleaseGateTests(unittest.TestCase):
    def test_valid_hash_bound_approval_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = make_release(root)
            result = verify_release_gate(
                root,
                approval,
                expected_tag=TAG,
                expected_source_commit=COMMIT,
                validate_model_runtime=False,
            )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["gate"], "D")

    def test_missing_approval_fails_closed(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ReleaseGateError, "Gate D approval"),
        ):
            verify_release_gate(
                directory,
                "release/gate-d-approval.json",
                expected_tag=TAG,
                expected_source_commit=COMMIT,
                validate_model_runtime=False,
            )

    def test_wrong_commit_or_decision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = make_release(root)
            payload = json.loads(approval.read_text(encoding="utf-8"))
            payload["decision"] = "pending"
            approval.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseGateError, "decision='approved'"):
                verify_release_gate(
                    root,
                    approval,
                    expected_tag=TAG,
                    expected_source_commit=COMMIT,
                    validate_model_runtime=False,
                )

            payload["decision"] = "approved"
            payload["sourceCommitSha"] = "b" * 40
            approval.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseGateError, "sourceCommitSha"):
                verify_release_gate(
                    root,
                    approval,
                    expected_tag=TAG,
                    expected_source_commit=COMMIT,
                    validate_model_runtime=False,
                )

    def test_stale_evidence_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = make_release(root)
            (root / "reports/results.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseGateError, "resultsSha256"):
                verify_release_gate(
                    root,
                    approval,
                    expected_tag=TAG,
                    expected_source_commit=COMMIT,
                    validate_model_runtime=False,
                )

    def test_results_must_be_explicitly_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = make_release(root)
            results_path = root / "reports/results.json"
            results_path.write_text(
                json.dumps({"schemaVersion": 1, "frozen": False}), encoding="utf-8"
            )
            approval_payload = json.loads(approval.read_text(encoding="utf-8"))
            approval_payload["evidence"]["resultsSha256"] = digest(results_path)
            approval.write_text(json.dumps(approval_payload), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseGateError, "frozen=true"):
                verify_release_gate(
                    root,
                    approval,
                    expected_tag=TAG,
                    expected_source_commit=COMMIT,
                    validate_model_runtime=False,
                )

    def test_manifest_must_bind_the_exact_model_and_tag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = make_release(root)
            manifest_path = root / "web/public/models/release.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["modelVersion"] = "v0.9.0"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            approval_payload = json.loads(approval.read_text(encoding="utf-8"))
            approval_payload["evidence"]["releaseManifestSha256"] = digest(manifest_path)
            approval.write_text(json.dumps(approval_payload), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseGateError, "modelVersion"):
                verify_release_gate(
                    root,
                    approval,
                    expected_tag=TAG,
                    expected_source_commit=COMMIT,
                    validate_model_runtime=False,
                )

    def test_runtime_validation_rejects_a_non_onnx_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = make_release(root)
            with self.assertRaisesRegex(ReleaseGateError, "structural/runtime"):
                verify_release_gate(
                    root,
                    approval,
                    expected_tag=TAG,
                    expected_source_commit=COMMIT,
                    validate_model_runtime=True,
                )

    def test_cli_returns_blocked_status_without_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status = main(
                [
                    "--repo-root",
                    directory,
                    "--expected-tag",
                    TAG,
                    "--expected-source-commit",
                    COMMIT,
                ]
            )
        self.assertEqual(status, 2)


if __name__ == "__main__":
    unittest.main()
