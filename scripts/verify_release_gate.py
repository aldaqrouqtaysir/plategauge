"""Fail-closed verification for a PlateGauge Gate D release checkout.

The verifier never creates or approves release evidence. It accepts only a
committed approval record whose hashes bind the frozen model, web release
manifest, machine-readable results, and claim-evidence map in the exact tag
checkout being deployed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUIRED_APPROVER = "Taysir Al Daqrouq"
MAX_MODEL_BYTES = 15_000_000
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
# A maintenance release may reuse a frozen model without rewriting any bound
# manifest bytes. Only these explicit release/model pairs are recognized.
MODEL_VERSION_BY_RELEASE = {"v1.0.0": "v1.0.0", "v1.0.1": "v1.0.0", "v1.0.2": "v1.0.0"}

MODEL_PATH = Path("web/public/models/plategauge.onnx")
RELEASE_MANIFEST_PATH = Path("web/public/models/release.json")
RESULTS_PATH = Path("reports/results.json")
CLAIM_EVIDENCE_PATH = Path("docs/CLAIM_EVIDENCE_MAP.csv")

APPROVAL_KEYS = {
    "schemaVersion",
    "gate",
    "decision",
    "approvedBy",
    "approvedAt",
    "releaseTag",
    "sourceCommitSha",
    "evidence",
}
EVIDENCE_KEYS = {
    "modelSha256",
    "releaseManifestSha256",
    "resultsSha256",
    "claimEvidenceSha256",
}


class ReleaseGateError(ValueError):
    """Raised when release evidence is absent, stale, malformed, or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ReleaseGateError(f"{label} must be a regular committed file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseGateError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseGateError(f"{label} must be a JSON object: {path}")
    return value


def _required_file(root: Path, relative: Path, label: str) -> Path:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise ReleaseGateError(f"Missing {label}: {relative.as_posix()}")
    return path


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ReleaseGateError(f"{label} must be 64 lowercase hexadecimal characters")
    return value


def _require_aware_timestamp(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseGateError("approvedAt must be a non-empty ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReleaseGateError("approvedAt must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReleaseGateError("approvedAt must include a UTC offset")


def _verify_release_manifest(
    manifest: dict[str, Any], *, expected_tag: str, model_sha256: str
) -> None:
    if expected_tag not in MODEL_VERSION_BY_RELEASE:
        raise ReleaseGateError("Unsupported release/model version binding")
    required = {
        "schemaVersion",
        "modelVersion",
        "modelPath",
        "modelSha256",
        "beforeInputName",
        "afterInputName",
        "outputName",
        "calibration",
    }
    if set(manifest) != required:
        raise ReleaseGateError("release.json fields differ from the frozen web schema")
    expected_values = {
        "schemaVersion": 1,
        "modelVersion": MODEL_VERSION_BY_RELEASE[expected_tag],
        "modelPath": "models/plategauge.onnx",
        "modelSha256": model_sha256,
        "beforeInputName": "before",
        "afterInputName": "after",
        "outputName": "quantiles",
    }
    for key, expected in expected_values.items():
        if manifest.get(key) != expected:
            raise ReleaseGateError(f"release.json {key} does not match the approved release")

    calibration = manifest.get("calibration")
    calibration_keys = {
        "lowerExpansion",
        "upperExpansion",
        "abstentionWidth",
        "intervalGatePassed",
    }
    if not isinstance(calibration, dict) or set(calibration) != calibration_keys:
        raise ReleaseGateError("release.json calibration fields differ from the frozen schema")
    for key in ("lowerExpansion", "upperExpansion"):
        value = calibration[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ReleaseGateError(f"release.json calibration.{key} must lie in [0, 1]")
    threshold = calibration["abstentionWidth"]
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not 0 < threshold <= 0.30
    ):
        raise ReleaseGateError("release.json calibration.abstentionWidth must lie in (0, 0.30]")
    if not isinstance(calibration["intervalGatePassed"], bool):
        raise ReleaseGateError("release.json calibration.intervalGatePassed must be boolean")


def _verify_onnx_runtime_contract(model_path: Path, manifest: dict[str, Any]) -> None:
    """Load and execute the frozen artifact using the release-time CPU runtime."""

    try:
        import numpy as np
        import onnx
        import onnxruntime as ort  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - release environment invariant
        raise ReleaseGateError(
            "ONNX release verification requires numpy, onnx, and onnxruntime"
        ) from exc

    try:
        graph = onnx.load(model_path, load_external_data=False)
        if any(
            initializer.data_location == onnx.TensorProto.EXTERNAL
            or bool(initializer.external_data)
            for initializer in graph.graph.initializer
        ):
            raise ReleaseGateError("Frozen ONNX model must not depend on external data files")
        onnx.checker.check_model(graph)
        session = ort.InferenceSession(
            model_path.read_bytes(), providers=["CPUExecutionProvider"]
        )
    except ReleaseGateError:
        raise
    except Exception as exc:
        raise ReleaseGateError("Frozen ONNX model failed structural/runtime loading") from exc

    inputs = session.get_inputs()
    outputs = session.get_outputs()
    expected_inputs = [manifest["beforeInputName"], manifest["afterInputName"]]
    if [value.name for value in inputs] != expected_inputs:
        raise ReleaseGateError("Frozen ONNX input names/order differ from release.json")
    if [value.name for value in outputs] != [manifest["outputName"]]:
        raise ReleaseGateError("Frozen ONNX output name differs from release.json")
    for value in inputs:
        if value.type != "tensor(float)" or len(value.shape) != 4:
            raise ReleaseGateError("Frozen ONNX inputs must be rank-4 float tensors")
        if list(value.shape[1:]) != [3, 224, 224]:
            raise ReleaseGateError("Frozen ONNX inputs must have shape [batch, 3, 224, 224]")
    if outputs[0].type != "tensor(float)" or len(outputs[0].shape) != 2:
        raise ReleaseGateError("Frozen ONNX output must be a rank-2 float tensor")
    if outputs[0].shape[1] != 3:
        raise ReleaseGateError("Frozen ONNX output must have shape [batch, 3]")

    zeros = np.zeros((1, 3, 224, 224), dtype=np.float32)
    try:
        predictions = np.asarray(
            session.run(
                [manifest["outputName"]],
                {manifest["beforeInputName"]: zeros, manifest["afterInputName"]: zeros},
            )[0]
        )
    except Exception as exc:
        raise ReleaseGateError("Frozen ONNX model failed the release smoke inference") from exc
    if predictions.shape != (1, 3) or not np.all(np.isfinite(predictions)):
        raise ReleaseGateError("Frozen ONNX smoke output is not one finite quantile triplet")
    if not np.all((predictions >= 0.0) & (predictions <= 1.0)):
        raise ReleaseGateError("Frozen ONNX smoke output lies outside [0, 1]")
    if not (predictions[0, 0] <= predictions[0, 1] <= predictions[0, 2]):
        raise ReleaseGateError("Frozen ONNX smoke output is not ordered")


def verify_release_gate(
    repo_root: str | Path,
    approval_path: str | Path,
    *,
    expected_tag: str,
    expected_source_commit: str,
    validate_model_runtime: bool = True,
) -> dict[str, Any]:
    """Verify committed Gate D approval and every hash-bound release artifact."""

    root = Path(repo_root).resolve()
    approval_file = Path(approval_path)
    if not approval_file.is_absolute():
        approval_file = root / approval_file
    approval = _json_object(approval_file, "Gate D approval")
    if set(approval) != APPROVAL_KEYS:
        raise ReleaseGateError("Gate D approval fields differ from schema version 1")
    if approval["schemaVersion"] != SCHEMA_VERSION:
        raise ReleaseGateError("Unsupported Gate D approval schemaVersion")
    if approval["gate"] != "D" or approval["decision"] != "approved":
        raise ReleaseGateError("Gate D must explicitly record decision='approved'")
    if approval["approvedBy"] != REQUIRED_APPROVER:
        raise ReleaseGateError(f"Gate D must be approved by {REQUIRED_APPROVER}")
    _require_aware_timestamp(approval["approvedAt"])
    if approval["releaseTag"] != expected_tag:
        raise ReleaseGateError("Gate D releaseTag does not match the deployed tag")
    if not COMMIT_PATTERN.fullmatch(expected_source_commit):
        raise ReleaseGateError("Expected source commit must be a full lowercase 40-character Git SHA")
    if approval["sourceCommitSha"] != expected_source_commit:
        raise ReleaseGateError("Gate D sourceCommitSha does not match the frozen source commit")

    evidence = approval["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS:
        raise ReleaseGateError("Gate D evidence fields differ from schema version 1")

    model_path = _required_file(root, MODEL_PATH, "frozen ONNX model")
    if model_path.stat().st_size > MAX_MODEL_BYTES:
        raise ReleaseGateError(
            f"Frozen ONNX model exceeds the 15 MB release ceiling: {model_path.stat().st_size}"
        )
    manifest_path = _required_file(root, RELEASE_MANIFEST_PATH, "web release manifest")
    results_path = _required_file(root, RESULTS_PATH, "machine-readable frozen results")
    claim_path = _required_file(root, CLAIM_EVIDENCE_PATH, "claim-evidence map")

    computed = {
        "modelSha256": sha256_file(model_path),
        "releaseManifestSha256": sha256_file(manifest_path),
        "resultsSha256": sha256_file(results_path),
        "claimEvidenceSha256": sha256_file(claim_path),
    }
    for key, actual in computed.items():
        approved = _require_sha256(evidence.get(key), f"evidence.{key}")
        if approved != actual:
            raise ReleaseGateError(f"Gate D evidence hash mismatch for {key}")

    release_manifest = _json_object(manifest_path, "web release manifest")
    _verify_release_manifest(
        release_manifest,
        expected_tag=expected_tag,
        model_sha256=computed["modelSha256"],
    )
    results = _json_object(results_path, "machine-readable frozen results")
    if results.get("schemaVersion") != 1 or results.get("frozen") is not True:
        raise ReleaseGateError(
            "results.json must declare schemaVersion=1 and frozen=true"
        )
    if validate_model_runtime:
        _verify_onnx_runtime_contract(model_path, release_manifest)

    return {
        "status": "verified",
        "gate": "D",
        "releaseTag": expected_tag,
        "sourceCommitSha": expected_source_commit,
        "approvedBy": approval["approvedBy"],
        "approvedAt": approval["approvedAt"],
        "modelSizeBytes": model_path.stat().st_size,
        "evidence": computed,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--approval",
        type=Path,
        default=Path("release/gate-d-approval.json"),
    )
    parser.add_argument("--expected-tag", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = verify_release_gate(
            arguments.repo_root,
            arguments.approval,
            expected_tag=arguments.expected_tag,
            expected_source_commit=arguments.expected_source_commit,
        )
    except ReleaseGateError as exc:
        print(
            json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
