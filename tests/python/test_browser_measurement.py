from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from test_release_staging import _fixture, _write_json

from plategauge.browser_benchmark import evaluate_browser_measurement
from plategauge.browser_measurement import (
    _default_observation_runner,
    collect_browser_measurement,
    compose_browser_measurement,
    validate_built_release,
)
from plategauge.errors import DataIntegrityError
from plategauge.release_staging import (
    build_web_release_manifest,
    validate_release_inputs,
)

TEST_BEFORE_BYTES = b"fixed-before"
TEST_AFTER_BYTES = b"fixed-after"
TEST_BEFORE_SHA256 = hashlib.sha256(TEST_BEFORE_BYTES).hexdigest()
TEST_AFTER_SHA256 = hashlib.sha256(TEST_AFTER_BYTES).hexdigest()


def _observation() -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "kind": "physical_browser_observation",
        "measured_at": "2026-09-20T12:00:00+04:00",
        "browser_name": "Chrome",
        "browser_version": "140.0.0.0",
        "browser_mode": "headed",
        "onnxruntime_web_version": "1.22.0",
        "manufacturer_model": "Example Manufacturer Example Laptop",
        "cpu": "Example CPU",
        "ram_gb": 16.0,
        "operating_system": "Windows 11",
        "warmup_runs": 3,
        "warm_inference_ms": [float(index) for index in range(1, 21)],
        "first_load_bytes": 25_000_000,
        "peak_application_memory_mb": 420.0,
        "memory_measurement_method": "performance.measureUserAgentSpecificMemory",
        "memory_measurement_notes": "Maximum of 24 genuine browser API samples.",
        "fixed_sample_id": "lefood-0192",
        "fixed_before_sha256": TEST_BEFORE_SHA256,
        "fixed_after_sha256": TEST_AFTER_SHA256,
        "numeric_prediction_recorded": False,
    }


def _built_release(root: Path, evidence: Path, results: Path) -> Path:
    inputs = validate_release_inputs(evidence_path=evidence, results_path=results)
    web_root = root / "web" / "dist"
    (web_root / "models").mkdir(parents=True)
    (web_root / "ort").mkdir()
    (web_root / "examples").mkdir()
    (web_root / "index.html").write_text("<html></html>", encoding="utf-8")
    (web_root / "ort" / "runtime.wasm").write_bytes(b"wasm")
    (web_root / "models" / "plategauge.onnx").write_bytes(inputs.model_path.read_bytes())
    (web_root / "examples" / "lefood-0192-before.jpg").write_bytes(TEST_BEFORE_BYTES)
    (web_root / "examples" / "lefood-0192-after.jpg").write_bytes(TEST_AFTER_BYTES)
    _write_json(
        web_root / "models" / "release.json",
        build_web_release_manifest(inputs, model_version="v1.0.0"),
    )
    return web_root


class BrowserMeasurementTests(unittest.TestCase):
    def test_composes_exact_measurement_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            inputs = validate_release_inputs(evidence_path=evidence, results_path=results)
            payload = compose_browser_measurement(
                observation=_observation(),
                release_inputs=inputs,
                device_label="Reference laptop",
                physical_device_confirmed=True,
            )
            self.assertEqual(payload["status"], "measured")
            self.assertTrue(payload["reference_device"]["physical_device"])
            self.assertEqual(payload["runtime"]["execution_provider"], "wasm")
            self.assertEqual(payload["runtime"]["browser_mode"], "headed")
            self.assertEqual(payload["benchmark_input"]["sample_id"], "lefood-0192")
            self.assertFalse(payload["benchmark_input"]["numeric_prediction_recorded"])
            self.assertEqual(len(payload["measurements"]["warm_inference_ms"]), 20)
            gate = evaluate_browser_measurement(
                payload,
                measurement_sha256="9" * 64,
                expected_model_sha256=inputs.model_sha256,
                expected_release_evidence_sha256=inputs.evidence_file_sha256,
            )
            self.assertEqual(gate["status"], "passed")

    def test_collects_through_injected_real_observer_contract_and_writes_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            web_root = _built_release(root, evidence, results)
            script = root / "web" / "scripts" / "observer.mjs"
            script.parent.mkdir(parents=True)
            script.write_text("// test observer", encoding="utf-8")
            output = root / "measurement.json"
            commands: list[list[str]] = []

            def runner(command: object, working_directory: Path, timeout: int) -> dict[str, Any]:
                commands.append(list(command))  # type: ignore[arg-type]
                self.assertEqual(working_directory, script.parent.parent)
                self.assertEqual(timeout, 60)
                return _observation()

            result = collect_browser_measurement(
                evidence_path=evidence,
                results_path=results,
                web_root=web_root,
                observer_script=script,
                output_path=output,
                device_label="Reference laptop",
                physical_device_confirmed=True,
                browser_channel="chrome",
                timeout_seconds=60,
                observation_runner=runner,
            )
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)
            self.assertIn("--browser-channel", commands[0])
            self.assertNotIn("--before-image", commands[0])
            self.assertNotIn("--after-image", commands[0])
            with self.assertRaisesRegex(DataIntegrityError, "already exists"):
                collect_browser_measurement(
                    evidence_path=evidence,
                    results_path=results,
                    web_root=web_root,
                    observer_script=script,
                    output_path=output,
                    device_label="Reference laptop",
                    physical_device_confirmed=True,
                    observation_runner=runner,
                )
            self.assertEqual(len(commands), 1)

    def test_fails_before_observation_without_physical_confirmation(self) -> None:
        called = False

        def runner(command: object, working_directory: Path, timeout: int) -> dict[str, Any]:
            del command, working_directory, timeout
            nonlocal called
            called = True
            return _observation()

        with self.assertRaisesRegex(DataIntegrityError, "physical reference device"):
            collect_browser_measurement(
                evidence_path="unused",
                results_path="unused",
                web_root="unused",
                observer_script="unused",
                output_path="unused",
                device_label="Reference",
                physical_device_confirmed=False,
                observation_runner=runner,
            )
        self.assertFalse(called)

    def test_collection_rejects_observer_mode_or_fixed_asset_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            web_root = _built_release(root, evidence, results)
            script = root / "web" / "scripts" / "observer.mjs"
            script.parent.mkdir(parents=True)
            script.write_text("// test observer", encoding="utf-8")
            common: dict[str, Any] = {
                "evidence_path": evidence,
                "results_path": results,
                "web_root": web_root,
                "observer_script": script,
                "device_label": "Reference laptop",
                "physical_device_confirmed": True,
            }

            headless_observation = _observation()
            headless_observation["browser_mode"] = "headless"
            with self.assertRaisesRegex(DataIntegrityError, "launch mode"):
                collect_browser_measurement(
                    **common,
                    output_path=root / "mode.json",
                    observation_runner=lambda *_: headless_observation,
                )

            drifted_observation = _observation()
            drifted_observation["fixed_before_sha256"] = "0" * 64
            with self.assertRaisesRegex(DataIntegrityError, "static-build bytes"):
                collect_browser_measurement(
                    **common,
                    output_path=root / "hash.json",
                    observation_runner=lambda *_: drifted_observation,
                )

    def test_rejects_unreliable_memory_or_insufficient_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            inputs = validate_release_inputs(evidence_path=evidence, results_path=results)
            unavailable = _observation()
            unavailable["memory_measurement_method"] = "unavailable"
            with self.assertRaisesRegex(DataIntegrityError, "measureUserAgentSpecificMemory"):
                compose_browser_measurement(
                    observation=unavailable,
                    release_inputs=inputs,
                    device_label="Reference",
                    physical_device_confirmed=True,
                )
            too_few = _observation()
            too_few["warm_inference_ms"] = [1.0]
            with self.assertRaisesRegex(DataIntegrityError, "At least 20"):
                compose_browser_measurement(
                    observation=too_few,
                    release_inputs=inputs,
                    device_label="Reference",
                    physical_device_confirmed=True,
                )

    def test_rejects_built_model_or_manifest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            inputs = validate_release_inputs(evidence_path=evidence, results_path=results)
            web_root = _built_release(root, evidence, results)
            self.assertEqual(
                validate_built_release(web_root=web_root, release_inputs=inputs), "v1.0.0"
            )
            (web_root / "models" / "plategauge.onnx").write_bytes(b"changed")
            with self.assertRaisesRegex(DataIntegrityError, "differs"):
                validate_built_release(web_root=web_root, release_inputs=inputs)

    def test_rejects_missing_build_assets_and_manifest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            inputs = validate_release_inputs(evidence_path=evidence, results_path=results)
            with self.assertRaisesRegex(DataIntegrityError, "regular directory"):
                validate_built_release(web_root=root / "missing", release_inputs=inputs)

            web_root = _built_release(root, evidence, results)
            (web_root / "index.html").unlink()
            with self.assertRaisesRegex(DataIntegrityError, "index"):
                validate_built_release(web_root=web_root, release_inputs=inputs)

            web_root = _built_release(root / "manifest", evidence, results)
            manifest_path = web_root / "models" / "release.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["modelVersion"] = 1
            _write_json(manifest_path, manifest)
            with self.assertRaisesRegex(DataIntegrityError, "modelVersion"):
                validate_built_release(web_root=web_root, release_inputs=inputs)

            web_root = _built_release(root / "calibration", evidence, results)
            manifest_path = web_root / "models" / "release.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["calibration"]["abstentionWidth"] = 0.2
            _write_json(manifest_path, manifest)
            with self.assertRaisesRegex(DataIntegrityError, "manifest differs"):
                validate_built_release(web_root=web_root, release_inputs=inputs)

            web_root = _built_release(root / "ort", evidence, results)
            (web_root / "ort" / "runtime.wasm").unlink()
            with self.assertRaisesRegex(DataIntegrityError, "WASM"):
                validate_built_release(web_root=web_root, release_inputs=inputs)

    def test_observer_runner_fail_closed_boundaries(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["node"], returncode=0, stdout=json.dumps(_observation()), stderr=""
        )
        with patch("plategauge.browser_measurement.subprocess.run", return_value=completed):
            self.assertEqual(
                _default_observation_runner(["node", "observer"], Path.cwd(), 10)["kind"],
                "physical_browser_observation",
            )
        failures = (
            (
                subprocess.CompletedProcess(
                    args=["node"], returncode=2, stdout="", stderr="memory unavailable"
                ),
                "observation failed",
            ),
            (
                subprocess.CompletedProcess(
                    args=["node"], returncode=0, stdout="not-json", stderr=""
                ),
                "one JSON object",
            ),
            (
                subprocess.CompletedProcess(args=["node"], returncode=0, stdout="[]", stderr=""),
                "JSON object",
            ),
        )
        for result, message in failures:
            with (
                self.subTest(message=message),
                patch("plategauge.browser_measurement.subprocess.run", return_value=result),
                self.assertRaisesRegex(DataIntegrityError, message),
            ):
                _default_observation_runner(["node"], Path.cwd(), 10)
        with (
            patch(
                "plategauge.browser_measurement.subprocess.run",
                side_effect=subprocess.TimeoutExpired("node", 10),
            ),
            self.assertRaisesRegex(DataIntegrityError, "could not complete"),
        ):
            _default_observation_runner(["node"], Path.cwd(), 10)

    def test_rejects_malformed_observation_fields_and_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            inputs = validate_release_inputs(evidence_path=evidence, results_path=results)
            cases: tuple[tuple[str, object, str], ...] = (
                ("fields", lambda value: value.__setitem__("extra", True), "fields differ"),
                ("identity", lambda value: value.__setitem__("kind", "other"), "identity"),
                ("physical", lambda value: None, "physical reference device"),
                ("timestamp", lambda value: value.__setitem__("measured_at", "bad"), "ISO-8601"),
                (
                    "timezone",
                    lambda value: value.__setitem__("measured_at", "2026-09-20T12:00:00"),
                    "timezone",
                ),
                ("warmups", lambda value: value.__setitem__("warmup_runs", 2), "At least 3"),
                (
                    "browser-mode",
                    lambda value: value.__setitem__("browser_mode", "unknown"),
                    "browser_mode",
                ),
                (
                    "sample",
                    lambda value: value.__setitem__("fixed_sample_id", "lefood-9999"),
                    "fixed sample",
                ),
                (
                    "asset-hash",
                    lambda value: value.__setitem__("fixed_before_sha256", "not-a-hash"),
                    "SHA-256",
                ),
                (
                    "prediction",
                    lambda value: value.__setitem__("numeric_prediction_recorded", True),
                    "must not record",
                ),
                (
                    "first-load",
                    lambda value: value.__setitem__("first_load_bytes", True),
                    "integer",
                ),
                (
                    "memory",
                    lambda value: value.__setitem__("peak_application_memory_mb", float("nan")),
                    "greater than zero",
                ),
                ("label", lambda value: None, "device_label"),
            )
            for name, mutation, message in cases:
                observation = _observation()
                mutation(observation)  # type: ignore[operator]
                confirmed = name != "physical"
                label = "" if name == "label" else "Reference"
                with self.subTest(name=name), self.assertRaisesRegex(DataIntegrityError, message):
                    compose_browser_measurement(
                        observation=observation,
                        release_inputs=inputs,
                        device_label=label,
                        physical_device_confirmed=confirmed,
                    )

    def test_rejects_invalid_collection_options_and_missing_inputs(self) -> None:
        common: dict[str, Any] = {
            "evidence_path": "unused",
            "results_path": "unused",
            "web_root": "unused",
            "observer_script": "unused",
            "output_path": "unused-output",
            "device_label": "Reference",
            "physical_device_confirmed": True,
        }
        cases = (
            ({"warmups": 2}, "below the frozen minimum"),
            ({"browser_channel": "firefox"}, "Unsupported browser"),
            ({"base_path": "relative"}, "base_path"),
            ({"timeout_seconds": 0}, "timeout_seconds"),
        )
        for override, message in cases:
            with (
                self.subTest(override=override),
                self.assertRaisesRegex(DataIntegrityError, message),
            ):
                collect_browser_measurement(**common, **override)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, evidence, results = _fixture(root)
            web_root = _built_release(root, evidence, results)
            with self.assertRaisesRegex(DataIntegrityError, "observer script"):
                collect_browser_measurement(
                    **{
                        **common,
                        "evidence_path": evidence,
                        "results_path": results,
                        "web_root": web_root,
                        "output_path": root / "output.json",
                    }
                )


if __name__ == "__main__":
    unittest.main()
