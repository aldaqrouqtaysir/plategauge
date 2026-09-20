from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.release_artifacts import canonical_json_sha256
from plategauge.release_staging import (
    build_web_release_manifest,
    stage_web_release,
    validate_release_inputs,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    model = root / "artifacts" / "plategauge.onnx"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"frozen-onnx-bytes")
    protocol_id = "1" * 64
    run_id = "2" * 64
    checkpoint_sha = "3" * 64
    manifest_sha = "4" * 64
    evidence_core: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "frozen_final_onnx_export",
        "status": "passed",
        "model_version": f"plategauge/{protocol_id[:12]}/{checkpoint_sha[:12]}",
        "model_identity": {
            "schema_version": "1.0",
            "protocol_id": protocol_id,
            "run_id": run_id,
            "runner_fingerprint": "5" * 64,
            "configuration": "M2",
            "epoch": 6,
            "dropout": 0.4,
            "uncertainty_policy": {
                "interval_correction": 0.035,
                "abstention_threshold": 0.30,
            },
            "checkpoint_size_bytes": 100,
            "hashes": {
                "checkpoint_sha256": checkpoint_sha,
                "manifest_sha256": manifest_sha,
            },
        },
        "dataset_verification": {"record_count": 524},
        "onnx": {
            "filename": "plategauge.onnx",
            "sha256": sha256_file(model),
            "model_bytes": model.stat().st_size,
            "maximum_allowed_bytes": 15_000_000,
            "opset_version": 18,
            "precision": "FP32",
            "inputs": {
                "before": ["batch", 3, 224, 224],
                "after": ["batch", 3, 224, 224],
            },
            "output": {"quantiles": ["batch", 3], "order": ["q05", "q50", "q95"]},
        },
        "parity": {
            "sample_count": 8,
            "sample_ids": [f"sample-{index}" for index in range(8)],
            "input_tensor_sha256": "6" * 64,
            "maximum_absolute_drift": 1e-6,
            "maximum_allowed_drift": 1e-4,
            "passed": True,
        },
        "export_metadata": {},
        "implicit_downloads_allowed": False,
    }
    evidence = evidence_core | {"evidence_sha256": canonical_json_sha256(evidence_core)}
    evidence_path = model.with_suffix(".onnx.evidence.json")
    _write_json(evidence_path, evidence)
    results = {
        "schemaVersion": 1,
        "frozen": True,
        "protocol_id": protocol_id,
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "uncertainty": {
            "interval_gate": {"passed": False},
            "public_interval_allowed": False,
        },
        "decisions": {
            "efficiency": {
                "model_sha256": sha256_file(model),
                "evidence_sha256": sha256_file(evidence_path),
                "model_size_bytes": model.stat().st_size,
                "parity_passed": True,
                "model_size_passed": True,
                "passed": True,
            },
            "stop": {"triggered": False},
            "release_recommendation": "benchmark_failure_explorer",
        },
    }
    results_path = root / "reports" / "results.json"
    _write_json(results_path, results)
    return model, evidence_path, results_path


def _rewrite_evidence(path: Path, payload: dict[str, object]) -> None:
    core = {key: value for key, value in payload.items() if key != "evidence_sha256"}
    payload["evidence_sha256"] = canonical_json_sha256(core)
    _write_json(path, payload)


class ReleaseStagingTests(unittest.TestCase):
    def test_validates_stages_and_resumes_identical_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, evidence, results = _fixture(root)
            output = root / "web" / "public" / "models"
            first = stage_web_release(
                evidence_path=evidence,
                results_path=results,
                output_directory=output,
                model_version="v1.0.0",
            )
            self.assertEqual(first["status"], "staged")
            self.assertEqual((output / "plategauge.onnx").read_bytes(), source.read_bytes())
            manifest = json.loads((output / "release.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["calibration"]["lowerExpansion"], 0.035)
            self.assertEqual(manifest["calibration"]["upperExpansion"], 0.035)
            self.assertEqual(manifest["calibration"]["abstentionWidth"], 0.30)
            self.assertFalse(manifest["calibration"]["intervalGatePassed"])

            second = stage_web_release(
                evidence_path=evidence,
                results_path=results,
                output_directory=output,
                model_version="v1.0.0",
            )
            self.assertEqual(second["status"], "verified_existing")

    def test_rejects_changed_staged_bytes_and_invalid_model_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            inputs = validate_release_inputs(evidence_path=evidence, results_path=results)
            with self.assertRaisesRegex(DataIntegrityError, "semantic release tag"):
                build_web_release_manifest(inputs, model_version="latest")
            output = root / "output"
            output.mkdir()
            (output / "plategauge.onnx").write_bytes(b"different")
            with self.assertRaisesRegex(DataIntegrityError, "differs"):
                stage_web_release(
                    evidence_path=evidence,
                    results_path=results,
                    output_directory=output,
                    model_version="v1.0.0",
                )

            manifest_only = root / "manifest-only"
            manifest_only.mkdir()
            (manifest_only / "release.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "differs"):
                stage_web_release(
                    evidence_path=evidence,
                    results_path=results,
                    output_directory=manifest_only,
                    model_version="v1.0.0",
                )
            self.assertFalse((manifest_only / "plategauge.onnx").exists())

    def test_rejects_tampered_evidence_model_and_results_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, evidence, results = _fixture(root)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            payload["evidence_sha256"] = "0" * 64
            _write_json(evidence, payload)
            with self.assertRaisesRegex(DataIntegrityError, "canonical digest"):
                validate_release_inputs(evidence_path=evidence, results_path=results)

            model, evidence, results = _fixture(root / "fresh")
            model.write_bytes(b"tampered")
            with self.assertRaisesRegex(DataIntegrityError, "do not match"):
                validate_release_inputs(evidence_path=evidence, results_path=results)

            _, evidence, results = _fixture(root / "identity")
            report = json.loads(results.read_text(encoding="utf-8"))
            report["run_id"] = "9" * 64
            _write_json(results, report)
            with self.assertRaisesRegex(DataIntegrityError, "identity differs"):
                validate_release_inputs(evidence_path=evidence, results_path=results)

    def test_rejects_inconsistent_interval_efficiency_and_stop_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            report = json.loads(results.read_text(encoding="utf-8"))
            report["uncertainty"]["public_interval_allowed"] = True
            _write_json(results, report)
            with self.assertRaisesRegex(DataIntegrityError, "interval publication"):
                validate_release_inputs(evidence_path=evidence, results_path=results)

            _, evidence, results = _fixture(root / "efficiency")
            report = json.loads(results.read_text(encoding="utf-8"))
            report["decisions"]["efficiency"]["passed"] = False
            _write_json(results, report)
            with self.assertRaisesRegex(DataIntegrityError, "efficiency decision"):
                validate_release_inputs(evidence_path=evidence, results_path=results)

            _, evidence, results = _fixture(root / "stop")
            report = json.loads(results.read_text(encoding="utf-8"))
            report["decisions"]["stop"]["triggered"] = True
            _write_json(results, report)
            with self.assertRaisesRegex(DataIntegrityError, "project-stop"):
                validate_release_inputs(evidence_path=evidence, results_path=results)

    def test_rejects_malformed_export_contracts(self) -> None:
        mutations: tuple[tuple[str, object, str], ...] = (
            ("extra", lambda value: value.__setitem__("extra", True), "fields differ"),
            ("status", lambda value: value.__setitem__("status", "failed"), "not a passed"),
            (
                "identity",
                lambda value: value.__setitem__("model_identity", None),
                "must be objects",
            ),
            (
                "onnx-fields",
                lambda value: value["onnx"].pop("precision"),  # type: ignore[union-attr]
                "fields differ",
            ),
            (
                "hashes",
                lambda value: value["model_identity"].__setitem__("hashes", None),  # type: ignore[union-attr]
                "lacks hashes",
            ),
            (
                "protocol-sha",
                lambda value: value["model_identity"].__setitem__("protocol_id", "bad"),  # type: ignore[union-attr]
                "SHA-256",
            ),
            (
                "correction",
                lambda value: value["model_identity"]["uncertainty_policy"].__setitem__(  # type: ignore[index,union-attr]
                    "interval_correction", True
                ),
                "must be numeric",
            ),
            (
                "threshold",
                lambda value: value["model_identity"]["uncertainty_policy"].__setitem__(  # type: ignore[index,union-attr]
                    "abstention_threshold", 0.31
                ),
                "must lie",
            ),
            (
                "model-version",
                lambda value: value.__setitem__("model_version", "wrong"),
                "model_version differs",
            ),
            (
                "filename",
                lambda value: value["onnx"].__setitem__("filename", "../model.onnx"),  # type: ignore[union-attr]
                "single plategauge",
            ),
            (
                "size",
                lambda value: value["onnx"].__setitem__("model_bytes", True),  # type: ignore[union-attr]
                "size violates",
            ),
            (
                "contract",
                lambda value: value["onnx"].__setitem__("opset_version", 17),  # type: ignore[union-attr]
                "runtime contract",
            ),
            (
                "drift",
                lambda value: value["parity"].__setitem__("maximum_absolute_drift", 0.1),  # type: ignore[union-attr]
                "must lie",
            ),
            (
                "parity",
                lambda value: value["parity"].__setitem__("passed", False),  # type: ignore[union-attr]
                "incomplete or failed",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, mutation, message in mutations:
                with self.subTest(name=name):
                    _, evidence, results = _fixture(root / name)
                    payload = json.loads(evidence.read_text(encoding="utf-8"))
                    mutation(payload)  # type: ignore[operator]
                    _rewrite_evidence(evidence, payload)
                    with self.assertRaisesRegex(DataIntegrityError, message):
                        validate_release_inputs(evidence_path=evidence, results_path=results)

    def test_rejects_malformed_results_and_output_directory(self) -> None:
        mutations: tuple[tuple[str, object, str], ...] = (
            ("schema", lambda value: value.__setitem__("schemaVersion", 2), "schemaVersion"),
            (
                "manifest",
                lambda value: value.__setitem__("manifest_sha256", "8" * 64),
                "manifest differs",
            ),
            (
                "uncertainty",
                lambda value: value.__setitem__("uncertainty", None),
                "lack uncertainty",
            ),
            (
                "decision-shape",
                lambda value: value["decisions"].__setitem__("stop", None),  # type: ignore[union-attr]
                "lack efficiency or stop",
            ),
            (
                "recommendation",
                lambda value: value["decisions"].__setitem__("release_recommendation", "no"),  # type: ignore[union-attr]
                "do not permit",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, mutation, message in mutations:
                with self.subTest(name=name):
                    _, evidence, results = _fixture(root / name)
                    report = json.loads(results.read_text(encoding="utf-8"))
                    mutation(report)  # type: ignore[operator]
                    _write_json(results, report)
                    with self.assertRaisesRegex(DataIntegrityError, message):
                        validate_release_inputs(evidence_path=evidence, results_path=results)

            _, evidence, results = _fixture(root / "directory")
            output_file = root / "not-a-directory"
            output_file.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "regular directory"):
                stage_web_release(
                    evidence_path=evidence,
                    results_path=results,
                    output_directory=output_file,
                    model_version="v1.0.0",
                )


if __name__ == "__main__":
    unittest.main()
