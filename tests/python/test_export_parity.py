from __future__ import annotations

import json
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

import numpy as np

from plategauge.export import (
    assert_onnx_parity,
    export_paired_onnx,
    write_web_release_manifest,
)
from plategauge.model import build_paired_model, torch_available

EXPORT_STACK_AVAILABLE = torch_available() and all(
    find_spec(name) is not None for name in ("timm", "onnx", "onnxruntime")
)


@unittest.skipUnless(EXPORT_STACK_AVAILABLE, "install the train and export extras")
class ExportParityTests(unittest.TestCase):
    def test_actual_mobilenet_contract_exports_with_parity(self) -> None:
        model = build_paired_model(pretrained=False, dropout=0.2)
        self.assertEqual(model.feature_dim, 1024)
        values = np.random.default_rng(20260919).normal(
            size=(1, 3, 224, 224)
        ).astype(np.float32)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "smoke.onnx"
            metadata = export_paired_onnx(
                model,
                path,
                model_version="test-only/not-a-release",
            )
            drift = assert_onnx_parity(model, path, values, values, tolerance=1e-4)
            self.assertLessEqual(drift, 1e-4)
            self.assertLessEqual(path.stat().st_size, 15 * 1024 * 1024)
            self.assertEqual(len(metadata["onnx_sha256"]), 64)

    def test_web_release_manifest_matches_browser_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "plategauge.onnx"
            model_path.write_bytes(b"test-only-model")
            manifest_path = root / "release.json"
            payload = write_web_release_manifest(
                model_path,
                manifest_path,
                model_version="test-only/not-a-release",
                lower_expansion=0.02,
                upper_expansion=0.03,
                abstention_width=0.25,
                interval_gate_passed=False,
            )
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, payload)
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertEqual(payload["modelPath"], "models/plategauge.onnx")
            self.assertEqual(len(payload["modelSha256"]), 64)
            self.assertEqual(payload["beforeInputName"], "before")
            self.assertEqual(payload["afterInputName"], "after")
            self.assertEqual(payload["outputName"], "quantiles")
            self.assertFalse(payload["calibration"]["intervalGatePassed"])

    def test_web_release_manifest_rejects_unsafe_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "plategauge.onnx"
            model_path.write_bytes(b"test-only-model")
            with self.assertRaisesRegex(ValueError, "finite"):
                write_web_release_manifest(
                    model_path,
                    root / "release.json",
                    model_version="test",
                    lower_expansion=float("nan"),
                    upper_expansion=0.0,
                    abstention_width=0.25,
                    interval_gate_passed=False,
                )
            with self.assertRaisesRegex(ValueError, "greater than zero"):
                write_web_release_manifest(
                    model_path,
                    root / "release.json",
                    model_version="test",
                    lower_expansion=0.0,
                    upper_expansion=0.0,
                    abstention_width=0.0,
                    interval_gate_passed=False,
                )
            with self.assertRaisesRegex(ValueError, "same-origin"):
                write_web_release_manifest(
                    model_path,
                    root / "release.json",
                    model_version="test",
                    model_public_path="https://example.com/model.onnx",
                    lower_expansion=0.0,
                    upper_expansion=0.0,
                    abstention_width=0.25,
                    interval_gate_passed=False,
                )


if __name__ == "__main__":
    unittest.main()
