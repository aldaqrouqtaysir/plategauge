"""Export a frozen paired checkpoint after the model/data gates have passed.

This entry point intentionally requires explicit paths and will not download or
silently substitute pretrained weights.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from plategauge.export import (
    assert_onnx_parity,
    export_paired_onnx,
    write_web_release_manifest,
)
from plategauge.model import build_paired_model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--dropout", type=float, choices=(0.2, 0.4), required=True)
    parser.add_argument("--web-release-manifest", type=Path)
    parser.add_argument("--lower-expansion", type=float)
    parser.add_argument("--upper-expansion", type=float)
    parser.add_argument("--abstention-width", type=float)
    parser.add_argument("--interval-gate-passed", action="store_true")
    arguments = parser.parse_args()

    try:
        import torch
    except ImportError as exc:
        raise SystemExit("Install the 'train' and 'export' extras before export") from exc
    model = build_paired_model(dropout=arguments.dropout, pretrained=False)
    payload = torch.load(arguments.checkpoint, map_location="cpu", weights_only=True)
    state_dict = payload.get("state_dict", payload)
    model.load_state_dict(state_dict, strict=True)
    metadata = export_paired_onnx(
        model, arguments.output, model_version=arguments.model_version
    )
    if arguments.output.stat().st_size > 15 * 1024 * 1024:
        raise SystemExit("Exported FP32 model exceeds the 15 MiB release gate")
    generator = np.random.default_rng(20260919)
    before = generator.normal(size=(1, 3, 224, 224)).astype(np.float32)
    after = generator.normal(size=(1, 3, 224, 224)).astype(np.float32)
    metadata["maximum_parity_drift"] = assert_onnx_parity(
        model, arguments.output, before, after, tolerance=1e-4
    )
    if arguments.web_release_manifest is not None:
        calibration = (
            arguments.lower_expansion,
            arguments.upper_expansion,
            arguments.abstention_width,
        )
        if any(value is None for value in calibration):
            raise SystemExit(
                "Web manifest requires --lower-expansion, --upper-expansion, and "
                "--abstention-width from frozen inner-OOF calibration"
            )
        metadata["web_release_manifest"] = write_web_release_manifest(
            arguments.output,
            arguments.web_release_manifest,
            model_version=arguments.model_version,
            lower_expansion=float(arguments.lower_expansion),
            upper_expansion=float(arguments.upper_expansion),
            abstention_width=float(arguments.abstention_width),
            interval_gate_passed=arguments.interval_gate_passed,
        )
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
