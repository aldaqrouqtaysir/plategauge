from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import nullcontext
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from plategauge.export import (
    assert_onnx_parity,
    export_paired_onnx,
    onnx_parity,
    write_web_release_manifest,
)
from plategauge.model import build_paired_model, torch_available
from plategauge.release_export import MAXIMUM_FP32_MODEL_BYTES
from scripts import export_model

EXPORT_STACK_AVAILABLE = torch_available() and all(
    find_spec(name) is not None for name in ("timm", "onnx", "onnxruntime")
)


class ParityValidationTests(unittest.TestCase):
    """Pure synthetic contract checks run without the optional export stack."""

    def setUp(self) -> None:
        self.inputs = np.zeros((1, 3, 224, 224), dtype=np.float32)

    def _mock_parity(self, expected: np.ndarray, actual: np.ndarray) -> float:
        model = Mock()
        model.return_value.cpu.return_value.numpy.return_value = expected
        fake_runtime = SimpleNamespace(
            InferenceSession=lambda *args, **kwargs: SimpleNamespace(
                run=lambda *args, **kwargs: [actual]
            )
        )
        fake_torch = SimpleNamespace(inference_mode=nullcontext, from_numpy=lambda value: value)
        with patch.dict("sys.modules", {"torch": fake_torch, "onnxruntime": fake_runtime}):
            return onnx_parity(model, "unused.onnx", self.inputs, self.inputs)

    def test_valid_outputs_preserve_float32_drift(self) -> None:
        expected = np.asarray([[0.1, 0.5, 0.9]], dtype=np.float32)
        actual = expected + np.float32(1e-6)
        self.assertEqual(self._mock_parity(expected, actual), float(np.max(np.abs(expected - actual))))

    def test_nonfinite_drift_cannot_pass(self) -> None:
        for drift in (np.nan, np.inf, -np.inf, -1.0):
            with (
                self.subTest(drift=drift),
                patch("plategauge.export.onnx_parity", return_value=drift),
                self.assertRaisesRegex(AssertionError, "finite and non-negative"),
            ):
                assert_onnx_parity(object(), "unused.onnx", self.inputs, self.inputs)

    def test_invalid_tolerance_fails_before_runtime(self) -> None:
        for tolerance in (np.nan, np.inf, -np.inf, -1.0):
            with self.subTest(tolerance=tolerance), patch("plategauge.export.onnx_parity") as checker:
                with self.assertRaisesRegex(ValueError, "tolerance"):
                    assert_onnx_parity(
                        object(), "unused.onnx", self.inputs, self.inputs, tolerance=tolerance
                    )
                checker.assert_not_called()
        with patch("plategauge.export.onnx_parity", return_value=0.0):
            self.assertEqual(
                assert_onnx_parity(object(), "unused.onnx", self.inputs, self.inputs, tolerance=0.0),
                0.0,
            )
        with (
            patch("plategauge.export.onnx_parity", return_value=0.1),
            self.assertRaisesRegex(AssertionError, "exceeds"),
        ):
            assert_onnx_parity(object(), "unused.onnx", self.inputs, self.inputs)

    def test_inputs_reject_nonfinite_empty_or_mismatched_shapes(self) -> None:
        for before, after in (
            (np.zeros((0, 3, 224, 224)), np.zeros((0, 3, 224, 224))),
            (np.zeros((1, 3, 223, 224)), np.zeros((1, 3, 223, 224))),
            (self.inputs, np.zeros((2, 3, 224, 224))),
            (np.full_like(self.inputs, np.nan), self.inputs),
            (self.inputs, np.full_like(self.inputs, np.inf)),
            (np.asarray(0.0), self.inputs),
        ):
            with self.subTest(before=before.shape, after=after.shape), self.assertRaises(ValueError):
                onnx_parity(object(), "unused.onnx", before, after)

    def test_outputs_reject_nonfinite_and_broadcastable_wrong_shapes(self) -> None:
        good = np.asarray([[0.1, 0.5, 0.9]], dtype=np.float32)
        for bad in (
            good.reshape(1, 1, 3),
            good.reshape(3),
            np.zeros((0, 3)),
            np.full_like(good, np.nan),
            np.full_like(good, np.inf),
        ):
            with self.subTest(shape=bad.shape):
                with self.assertRaisesRegex(ValueError, "outputs"):
                    self._mock_parity(good, bad)
                with self.assertRaisesRegex(ValueError, "outputs"):
                    self._mock_parity(bad, good)


class ExportCliLimitTests(unittest.TestCase):
    def test_generic_cli_uses_canonical_decimal_byte_limit(self) -> None:
        self.assertEqual(MAXIMUM_FP32_MODEL_BYTES, 15_000_000)
        for size in (14_999_999, 15_000_000, 15_000_001, 15 * 1024 * 1024):
            output = Mock(spec=Path)
            output.stat.return_value.st_size = size
            arguments = SimpleNamespace(
                checkpoint=Path("unused.pt"),
                output=output,
                model_version="synthetic-contract-test",
                dropout=0.2,
                web_release_manifest=None,
            )
            fake_torch = SimpleNamespace(load=Mock(return_value={"state_dict": {}}))
            with (
                self.subTest(size=size),
                patch.object(export_model.argparse.ArgumentParser, "parse_args", return_value=arguments),
                patch.object(export_model, "build_paired_model"),
                patch.object(export_model, "export_paired_onnx", return_value={}),
                patch.object(export_model, "assert_onnx_parity", return_value=0.0) as parity,
                patch.dict("sys.modules", {"torch": fake_torch}),
                patch("builtins.print"),
            ):
                if size > MAXIMUM_FP32_MODEL_BYTES:
                    with self.assertRaisesRegex(SystemExit, "15,000,000-byte"):
                        export_model.main()
                    parity.assert_not_called()
                else:
                    self.assertEqual(export_model.main(), 0)
                    parity.assert_called_once()


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
            self.assertLessEqual(path.stat().st_size, MAXIMUM_FP32_MODEL_BYTES)
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
