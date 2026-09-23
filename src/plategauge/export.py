"""ONNX export, checksum, and runtime parity checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .data import sha256_file
from .errors import missing_extra


def export_paired_onnx(
    model: Any,
    output_path: str | Path,
    *,
    model_version: str,
    opset_version: int = 18,
    dynamic_batch: bool = True,
) -> dict[str, Any]:
    """Export the frozen paired model and a checksum-bearing metadata sidecar."""

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise missing_extra("ONNX export", "export", "torch") from exc
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    model = model.eval().cpu()
    before = torch.zeros((1, 3, 224, 224), dtype=torch.float32)
    after = torch.zeros((1, 3, 224, 224), dtype=torch.float32)
    dynamic_axes = None
    if dynamic_batch:
        dynamic_axes = {
            "before": {0: "batch"},
            "after": {0: "batch"},
            "quantiles": {0: "batch"},
        }
    torch.onnx.export(
        model,
        (before, after),
        path,
        input_names=["before", "after"],
        output_names=["quantiles"],
        dynamic_axes=dynamic_axes,
        opset_version=opset_version,
        do_constant_folding=True,
        dynamo=False,
    )
    metadata = {
        "schema_version": "1.0",
        "model_version": model_version,
        "onnx_sha256": sha256_file(path),
        "opset_version": opset_version,
        "inputs": {"before": ["batch", 3, 224, 224], "after": ["batch", 3, 224, 224]},
        "output": {"quantiles": ["batch", 3], "order": ["q05", "q50", "q95"]},
    }
    sidecar = path.with_suffix(path.suffix + ".json")
    sidecar.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def onnx_parity(
    model: Any,
    onnx_path: str | Path,
    before: np.ndarray,
    after: np.ndarray,
) -> float:
    """Return maximum absolute PyTorch/ONNX prediction drift."""

    before_array = np.asarray(before, dtype=np.float32)
    after_array = np.asarray(after, dtype=np.float32)
    if (
        before_array.ndim != 4
        or before_array.shape[0] < 1
        or before_array.shape[1:] != (3, 224, 224)
        or after_array.shape != before_array.shape
        or not np.isfinite(before_array).all()
        or not np.isfinite(after_array).all()
    ):
        raise ValueError("Parity inputs must be finite, matching [batch, 3, 224, 224] arrays")
    try:
        import onnxruntime as ort  # type: ignore[import-untyped]
        import torch
    except ImportError as exc:  # pragma: no cover - environment-dependent
        package = "onnxruntime" if "onnxruntime" in str(exc) else "torch"
        raise missing_extra("ONNX parity", "export", package) from exc
    with torch.inference_mode():
        expected = model(
            torch.from_numpy(before_array), torch.from_numpy(after_array)
        ).cpu().numpy()
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    actual = session.run(
        ["quantiles"], {"before": before_array, "after": after_array}
    )[0]
    expected = np.asarray(expected)
    actual = np.asarray(actual)
    output_shape = (before_array.shape[0], 3)
    if (
        expected.shape != output_shape
        or actual.shape != output_shape
        or not np.isfinite(expected).all()
        or not np.isfinite(actual).all()
    ):
        raise ValueError("Parity outputs must be finite, matching [batch, 3] arrays")
    return float(np.max(np.abs(expected - actual)))


def assert_onnx_parity(
    model: Any,
    onnx_path: str | Path,
    before: np.ndarray,
    after: np.ndarray,
    *,
    tolerance: float = 1e-4,
) -> float:
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Parity tolerance must be finite and non-negative")
    drift = onnx_parity(model, onnx_path, before, after)
    if not np.isfinite(drift) or drift < 0:
        raise AssertionError("ONNX drift must be finite and non-negative")
    if drift > tolerance:
        raise AssertionError(f"ONNX drift {drift:.8g} exceeds tolerance {tolerance:.8g}")
    return drift


def write_web_release_manifest(
    onnx_path: str | Path,
    output_path: str | Path,
    *,
    model_version: str,
    model_public_path: str = "models/plategauge.onnx",
    lower_expansion: float,
    upper_expansion: float,
    abstention_width: float,
    interval_gate_passed: bool,
) -> dict[str, Any]:
    """Write the exact checksum-bearing schema consumed by the browser worker."""

    model_path = Path(onnx_path)
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    values = (lower_expansion, upper_expansion, abstention_width)
    if not all(np.isfinite(values)) or not all(0.0 <= value <= 1.0 for value in values):
        raise ValueError("Release calibration values must be finite and in [0, 1]")
    if abstention_width == 0.0:
        raise ValueError("abstention_width must be greater than zero")
    if not model_public_path.startswith("models/") or not model_public_path.endswith(".onnx"):
        raise ValueError("model_public_path must be a same-origin models/*.onnx path")
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": model_version,
        "modelPath": model_public_path,
        "modelSha256": sha256_file(model_path),
        "beforeInputName": "before",
        "afterInputName": "after",
        "outputName": "quantiles",
        "calibration": {
            "lowerExpansion": lower_expansion,
            "upperExpansion": upper_expansion,
            "abstentionWidth": abstention_width,
            "intervalGatePassed": interval_gate_passed,
        },
    }
    manifest_path = Path(output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload
