from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plategauge.browser_benchmark import (
    evaluate_browser_benchmark_files,
    evaluate_browser_measurement,
)
from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError


def _measurement(model_sha: str = "a" * 64, evidence_sha: str = "b" * 64) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "kind": "browser_benchmark_measurement",
        "status": "measured",
        "model_sha256": model_sha,
        "release_evidence_sha256": evidence_sha,
        "measured_at": "2026-09-19T21:00:00+04:00",
        "reference_device": {
            "label": "documented reference laptop",
            "manufacturer_model": "Example model recorded by operator",
            "cpu": "Example CPU recorded by operator",
            "ram_gb": 16,
            "operating_system": "Example OS recorded by operator",
            "physical_device": True,
        },
        "runtime": {
            "browser_name": "Chrome",
            "browser_version": "measured-version",
            "onnxruntime_web_version": "1.22.0",
            "execution_provider": "wasm",
            "wasm_threads": 1,
            "webgpu_enabled": False,
            "build_source": "local_static_build",
        },
        "measurements": {
            "warmup_runs": 3,
            "warm_inference_ms": [float(value) for value in range(1, 21)],
            "first_load_bytes": 12_345_678,
            "peak_application_memory_mb": 400.0,
            "memory_measurement_method": "browser_process_rss",
            "memory_measurement_notes": "Peak delta recorded around paired inference.",
        },
    }


class BrowserBenchmarkTests(unittest.TestCase):
    def test_passes_and_uses_nearest_rank_percentiles(self) -> None:
        report = evaluate_browser_measurement(
            _measurement(),
            measurement_sha256="c" * 64,
            expected_model_sha256="a" * 64,
            expected_release_evidence_sha256="b" * 64,
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["derived"]["warm_p50_ms"], 10.0)
        self.assertEqual(report["derived"]["warm_p95_ms"], 19.0)
        self.assertTrue(report["gates"]["all_passed"])
        self.assertFalse(report["claim_limits"]["phone_performance_claim_allowed"])

    def test_fails_gate_but_preserves_real_observations(self) -> None:
        measurement = _measurement()
        measurement["measurements"]["warm_inference_ms"][-1] = 2000.0  # type: ignore[index]
        measurement["measurements"]["warm_inference_ms"][-2] = 1800.0  # type: ignore[index]
        measurement["measurements"]["peak_application_memory_mb"] = 600.0  # type: ignore[index]
        report = evaluate_browser_measurement(
            measurement,
            measurement_sha256="c" * 64,
            expected_model_sha256="a" * 64,
            expected_release_evidence_sha256="b" * 64,
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["derived"]["warm_p95_ms"], 1800.0)
        self.assertEqual(report["reported"]["peak_application_memory_mb"], 600.0)

    def test_rejects_unmeasured_or_unbound_records(self) -> None:
        pending = _measurement()
        pending["status"] = "pending"
        with self.assertRaisesRegex(DataIntegrityError, "real"):
            evaluate_browser_measurement(
                pending,
                measurement_sha256="c" * 64,
                expected_model_sha256="a" * 64,
                expected_release_evidence_sha256="b" * 64,
            )
        with self.assertRaisesRegex(DataIntegrityError, "different ONNX"):
            evaluate_browser_measurement(
                _measurement(),
                measurement_sha256="c" * 64,
                expected_model_sha256="d" * 64,
                expected_release_evidence_sha256="b" * 64,
            )
        too_few = _measurement()
        too_few["measurements"]["warm_inference_ms"] = [1.0]  # type: ignore[index]
        with self.assertRaisesRegex(DataIntegrityError, "At least 20"):
            evaluate_browser_measurement(
                too_few,
                measurement_sha256="c" * 64,
                expected_model_sha256="a" * 64,
                expected_release_evidence_sha256="b" * 64,
            )

    def test_file_evaluator_binds_bytes_and_writes_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.onnx"
            evidence = root / "model.evidence.json"
            measurement_path = root / "measurement.json"
            output = root / "gate.json"
            model.write_bytes(b"model-bytes")
            evidence.write_text('{"evidence":true}\n', encoding="utf-8")
            measurement = _measurement(sha256_file(model), sha256_file(evidence))
            measurement_path.write_text(
                json.dumps(measurement, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            report = evaluate_browser_benchmark_files(
                measurement_path=measurement_path,
                model_path=model,
                release_evidence_path=evidence,
                output_path=output,
            )
            self.assertEqual(report["status"], "passed")
            with self.assertRaisesRegex(DataIntegrityError, "already exists"):
                evaluate_browser_benchmark_files(
                    measurement_path=measurement_path,
                    model_path=model,
                    release_evidence_path=evidence,
                    output_path=output,
                )


if __name__ == "__main__":
    unittest.main()
