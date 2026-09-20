"""Fail-closed staging of frozen ONNX bytes for the static browser build.

This module does not export a model, alter frozen evaluation reports, or
authorize a public release.  It validates the canonical export evidence and
the active frozen results, then atomically publishes the exact ONNX bytes and
the browser manifest into a local web asset directory.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data import sha256_file
from .errors import DataIntegrityError
from .release_artifacts import canonical_json_sha256, read_json_object

EXPORT_SCHEMA_VERSION = "1.0"
RESULTS_SCHEMA_VERSION = 1
MAXIMUM_RELEASE_MODEL_BYTES = 15_000_000
MAXIMUM_ONNX_DRIFT = 1e-4
MODEL_VERSION_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

EXPORT_EVIDENCE_KEYS = {
    "schema_version",
    "kind",
    "status",
    "model_version",
    "model_identity",
    "dataset_verification",
    "onnx",
    "parity",
    "export_metadata",
    "implicit_downloads_allowed",
    "evidence_sha256",
}
ONNX_KEYS = {
    "filename",
    "sha256",
    "model_bytes",
    "maximum_allowed_bytes",
    "opset_version",
    "precision",
    "inputs",
    "output",
}
PARITY_KEYS = {
    "sample_count",
    "sample_ids",
    "input_tensor_sha256",
    "maximum_absolute_drift",
    "maximum_allowed_drift",
    "passed",
}


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise DataIntegrityError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _finite_number(
    value: object,
    label: str,
    *,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataIntegrityError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise DataIntegrityError(f"{label} must lie in [{minimum}, {maximum}]")
    return number


def _regular_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise DataIntegrityError(f"{label} must be a regular file: {path}")
    return path


@dataclass(frozen=True, slots=True)
class ValidatedReleaseInputs:
    """Validated identities and values needed to stage or benchmark a release."""

    model_path: Path
    model_sha256: str
    model_size_bytes: int
    evidence_path: Path
    evidence_file_sha256: str
    results_path: Path
    results_sha256: str
    protocol_id: str
    run_id: str
    source_model_version: str
    interval_correction: float
    abstention_threshold: float
    interval_gate_passed: bool
    release_recommendation: str


def validate_release_inputs(
    *,
    evidence_path: str | Path,
    results_path: str | Path,
) -> ValidatedReleaseInputs:
    """Validate the canonical exporter sidecar and matching frozen results."""

    evidence_file = _regular_file(Path(evidence_path), "Export evidence")
    results_file = _regular_file(Path(results_path), "Frozen results")
    evidence = read_json_object(evidence_file)
    if set(evidence) != EXPORT_EVIDENCE_KEYS:
        raise DataIntegrityError("Export evidence fields differ from schema 1.0")
    if (
        evidence.get("schema_version") != EXPORT_SCHEMA_VERSION
        or evidence.get("kind") != "frozen_final_onnx_export"
        or evidence.get("status") != "passed"
        or evidence.get("implicit_downloads_allowed") is not False
    ):
        raise DataIntegrityError("Export evidence is not a passed frozen ONNX export")
    embedded_digest = _sha(evidence.get("evidence_sha256"), "Export evidence digest")
    evidence_core = {key: value for key, value in evidence.items() if key != "evidence_sha256"}
    if canonical_json_sha256(evidence_core) != embedded_digest:
        raise DataIntegrityError("Export evidence canonical digest mismatch")

    identity = evidence.get("model_identity")
    onnx = evidence.get("onnx")
    parity = evidence.get("parity")
    if not isinstance(identity, dict) or not isinstance(onnx, dict) or not isinstance(parity, dict):
        raise DataIntegrityError("Export evidence identity, ONNX, and parity must be objects")
    if set(onnx) != ONNX_KEYS or set(parity) != PARITY_KEYS:
        raise DataIntegrityError("Export evidence ONNX or parity fields differ from schema 1.0")

    protocol_id = _sha(identity.get("protocol_id"), "Model protocol_id")
    run_id = _sha(identity.get("run_id"), "Model run_id")
    hashes = identity.get("hashes")
    policy = identity.get("uncertainty_policy")
    if not isinstance(hashes, dict) or not isinstance(policy, dict):
        raise DataIntegrityError("Model identity lacks hashes or uncertainty policy")
    checkpoint_sha = _sha(hashes.get("checkpoint_sha256"), "Checkpoint hash")
    manifest_sha = _sha(hashes.get("manifest_sha256"), "Manifest hash")
    correction = _finite_number(
        policy.get("interval_correction"), "Interval correction"
    )
    threshold = _finite_number(
        policy.get("abstention_threshold"),
        "Abstention threshold",
        minimum=1e-12,
        maximum=0.30,
    )

    source_model_version = evidence.get("model_version")
    expected_source_version = f"plategauge/{protocol_id[:12]}/{checkpoint_sha[:12]}"
    if source_model_version != expected_source_version:
        raise DataIntegrityError("Export model_version differs from its frozen identity")

    filename = onnx.get("filename")
    if not isinstance(filename, str) or Path(filename).name != filename or filename != "plategauge.onnx":
        raise DataIntegrityError("Export evidence must name the single plategauge.onnx artifact")
    model_sha = _sha(onnx.get("sha256"), "ONNX hash")
    model_bytes = onnx.get("model_bytes")
    if (
        not isinstance(model_bytes, int)
        or isinstance(model_bytes, bool)
        or model_bytes < 1
        or model_bytes > MAXIMUM_RELEASE_MODEL_BYTES
    ):
        raise DataIntegrityError("ONNX model size violates the 15,000,000-byte release ceiling")
    if (
        onnx.get("opset_version") != 18
        or onnx.get("precision") != "FP32"
        or onnx.get("inputs")
        != {"before": ["batch", 3, 224, 224], "after": ["batch", 3, 224, 224]}
        or onnx.get("output")
        != {"quantiles": ["batch", 3], "order": ["q05", "q50", "q95"]}
    ):
        raise DataIntegrityError("ONNX runtime contract differs from the browser release contract")
    drift = _finite_number(
        parity.get("maximum_absolute_drift"),
        "PyTorch/ONNX drift",
        maximum=MAXIMUM_ONNX_DRIFT,
    )
    del drift
    if (
        parity.get("passed") is not True
        or parity.get("maximum_allowed_drift") != MAXIMUM_ONNX_DRIFT
        or parity.get("sample_count") != 8
    ):
        raise DataIntegrityError("ONNX parity evidence is incomplete or failed")

    model = _regular_file(evidence_file.parent / filename, "Frozen ONNX model")
    if model.stat().st_size != model_bytes or sha256_file(model) != model_sha:
        raise DataIntegrityError("Frozen ONNX bytes do not match export evidence")

    results = read_json_object(results_file)
    if results.get("schemaVersion") != RESULTS_SCHEMA_VERSION or results.get("frozen") is not True:
        raise DataIntegrityError("Results must declare schemaVersion=1 and frozen=true")
    if results.get("protocol_id") != protocol_id or results.get("run_id") != run_id:
        raise DataIntegrityError("Results identity differs from the exported final model")
    if results.get("manifest_sha256") != manifest_sha:
        raise DataIntegrityError("Results manifest differs from the exported final model")

    uncertainty = results.get("uncertainty")
    decisions = results.get("decisions")
    if not isinstance(uncertainty, dict) or not isinstance(decisions, dict):
        raise DataIntegrityError("Results lack uncertainty or decision evidence")
    interval_gate = uncertainty.get("interval_gate")
    public_interval = uncertainty.get("public_interval_allowed")
    if (
        not isinstance(interval_gate, dict)
        or not isinstance(interval_gate.get("passed"), bool)
        or not isinstance(public_interval, bool)
        or public_interval is not interval_gate["passed"]
    ):
        raise DataIntegrityError("Results interval publication decision is inconsistent")
    efficiency = decisions.get("efficiency")
    stop = decisions.get("stop")
    recommendation = decisions.get("release_recommendation")
    if not isinstance(efficiency, dict) or not isinstance(stop, dict):
        raise DataIntegrityError("Results lack efficiency or stop decisions")
    if (
        efficiency.get("model_sha256") != model_sha
        or efficiency.get("evidence_sha256") != sha256_file(evidence_file)
        or efficiency.get("model_size_bytes") != model_bytes
        or efficiency.get("parity_passed") is not True
        or efficiency.get("model_size_passed") is not True
        or efficiency.get("passed") is not True
    ):
        raise DataIntegrityError("Results efficiency decision is not bound to this export")
    if stop.get("triggered") is not False:
        raise DataIntegrityError("A project-stop result cannot be staged as a browser release")
    if recommendation not in {"numeric_estimator_candidate", "benchmark_failure_explorer"}:
        raise DataIntegrityError("Results do not permit a browser release candidate")

    return ValidatedReleaseInputs(
        model_path=model.resolve(),
        model_sha256=model_sha,
        model_size_bytes=model_bytes,
        evidence_path=evidence_file.resolve(),
        evidence_file_sha256=sha256_file(evidence_file),
        results_path=results_file.resolve(),
        results_sha256=sha256_file(results_file),
        protocol_id=protocol_id,
        run_id=run_id,
        source_model_version=expected_source_version,
        interval_correction=correction,
        abstention_threshold=threshold,
        interval_gate_passed=public_interval,
        release_recommendation=str(recommendation),
    )


def build_web_release_manifest(
    inputs: ValidatedReleaseInputs,
    *,
    model_version: str,
) -> dict[str, Any]:
    """Build the exact manifest consumed by the browser worker."""

    if not MODEL_VERSION_PATTERN.fullmatch(model_version):
        raise DataIntegrityError("model_version must be an explicit semantic release tag")
    return {
        "schemaVersion": 1,
        "modelVersion": model_version,
        "modelPath": "models/plategauge.onnx",
        "modelSha256": inputs.model_sha256,
        "beforeInputName": "before",
        "afterInputName": "after",
        "outputName": "quantiles",
        "calibration": {
            "lowerExpansion": inputs.interval_correction,
            "upperExpansion": inputs.interval_correction,
            "abstentionWidth": inputs.abstention_threshold,
            "intervalGatePassed": inputs.interval_gate_passed,
        },
    }


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (json.dumps(dict(value), indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise DataIntegrityError(f"Release manifest is not finite JSON: {exc}") from exc


def _publish_bytes_resumable(destination: Path, expected: bytes) -> bool:
    """Atomically publish bytes, or verify and reuse an identical existing file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        _regular_file(destination, "Existing staged artifact")
        if destination.read_bytes() != expected:
            raise DataIntegrityError(f"Existing staged artifact differs: {destination}")
        return False

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_name = handle.name
        temporary = Path(temporary_name)
        if temporary.read_bytes() != expected:
            raise DataIntegrityError("Temporary staged artifact changed before publication")
        try:
            os.link(temporary, destination)
        except FileExistsError:
            _regular_file(destination, "Concurrent staged artifact")
            if destination.read_bytes() != expected:
                raise DataIntegrityError(
                    f"Concurrent staged artifact differs: {destination}"
                ) from None
            return False
        return True
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _preflight_existing(destination: Path, expected: bytes) -> None:
    if not destination.exists() and not destination.is_symlink():
        return
    _regular_file(destination, "Existing staged artifact")
    if destination.read_bytes() != expected:
        raise DataIntegrityError(f"Existing staged artifact differs: {destination}")


def stage_web_release(
    *,
    evidence_path: str | Path,
    results_path: str | Path,
    output_directory: str | Path,
    model_version: str,
) -> dict[str, Any]:
    """Stage exact model bytes and manifest without overwriting existing files."""

    inputs = validate_release_inputs(evidence_path=evidence_path, results_path=results_path)
    manifest = build_web_release_manifest(inputs, model_version=model_version)
    output = Path(output_directory)
    if output.exists() and (not output.is_dir() or output.is_symlink()):
        raise DataIntegrityError(f"Release output must be a regular directory: {output}")
    model_output = output / "plategauge.onnx"
    manifest_output = output / "release.json"
    model_bytes = inputs.model_path.read_bytes()
    manifest_bytes = _json_bytes(manifest)
    # Check every existing target before creating either missing target. This
    # prevents a mismatch in one member from producing a new partial pair.
    _preflight_existing(model_output, model_bytes)
    _preflight_existing(manifest_output, manifest_bytes)
    model_created = _publish_bytes_resumable(model_output, model_bytes)
    manifest_created = _publish_bytes_resumable(manifest_output, manifest_bytes)
    if (
        model_output.stat().st_size != inputs.model_size_bytes
        or sha256_file(model_output) != inputs.model_sha256
        or read_json_object(manifest_output) != manifest
    ):
        raise DataIntegrityError("Staged browser release failed final byte verification")
    return {
        "status": "staged" if model_created or manifest_created else "verified_existing",
        "model": str(model_output),
        "manifest": str(manifest_output),
        "model_sha256": inputs.model_sha256,
        "manifest_sha256": sha256_file(manifest_output),
        "export_evidence_sha256": inputs.evidence_file_sha256,
        "results_sha256": inputs.results_sha256,
        "protocol_id": inputs.protocol_id,
        "run_id": inputs.run_id,
        "model_version": model_version,
        "release_recommendation": inputs.release_recommendation,
        "public_interval_allowed": inputs.interval_gate_passed,
    }
