"""Hash-bound ONNX export evidence for the validated final checkpoint."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .data import sha256_file
from .errors import DataIntegrityError
from .export import export_paired_onnx, onnx_parity
from .release_artifacts import (
    EXPECTED_VALID_PAIRS,
    FrozenFinalArtifact,
    canonical_json_sha256,
    write_immutable_json,
)
from .schema import read_manifest
from .transforms import deterministic_preprocess

EXPORT_EVIDENCE_SCHEMA_VERSION = "1.0"
# The frozen charter says 15 MB and the Gate C aggregator interprets that as
# decimal megabytes. Keep export and aggregation on the same exact ceiling.
MAXIMUM_FP32_MODEL_BYTES = 15_000_000
MAXIMUM_ONNX_DRIFT = 1e-4
PARITY_SAMPLE_COUNT = 8

Exporter = Callable[..., dict[str, Any]]
ParityChecker = Callable[[Any, str | Path, np.ndarray, np.ndarray], float]


def _array_pair_sha256(before: np.ndarray, after: np.ndarray) -> str:
    digest = hashlib.sha256()
    for label, value in ((b"before\0", before), (b"after\0", after)):
        array = np.ascontiguousarray(value, dtype="<f4")
        digest.update(label)
        digest.update(str(array.shape).encode("ascii"))
        digest.update(b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _parity_inputs(
    artifact: FrozenFinalArtifact,
    dataset_root: str | Path,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    records = sorted(
        (record for record in read_manifest(artifact.manifest_path) if record.is_valid),
        key=lambda record: record.sample_id,
    )
    if len(records) != EXPECTED_VALID_PAIRS:
        raise DataIntegrityError("ONNX parity requires the frozen 514-pair manifest")
    selected = records[:PARITY_SAMPLE_COUNT]
    root = Path(dataset_root)
    before = np.stack(
        [deterministic_preprocess(root / record.before_path) for record in selected]
    ).astype(np.float32, copy=False)
    after = np.stack(
        [deterministic_preprocess(root / record.after_path) for record in selected]
    ).astype(np.float32, copy=False)
    return [record.sample_id for record in selected], before, after


def compose_export_evidence(
    *,
    artifact: FrozenFinalArtifact,
    dataset_verification: Mapping[str, Any],
    model_filename: str,
    model_sha256: str,
    model_bytes: int,
    export_metadata: Mapping[str, Any],
    parity_sample_ids: list[str],
    parity_input_sha256: str,
    maximum_parity_drift: float,
) -> dict[str, Any]:
    """Compose evidence only when both frozen efficiency gates pass."""

    if model_bytes < 1 or model_bytes > MAXIMUM_FP32_MODEL_BYTES:
        raise DataIntegrityError(
            f"FP32 ONNX artifact is {model_bytes} bytes; maximum is {MAXIMUM_FP32_MODEL_BYTES}"
        )
    if (
        not np.isfinite(maximum_parity_drift)
        or maximum_parity_drift < 0
        or maximum_parity_drift > MAXIMUM_ONNX_DRIFT
    ):
        raise DataIntegrityError(
            f"PyTorch/ONNX drift {maximum_parity_drift!r} exceeds {MAXIMUM_ONNX_DRIFT}"
        )
    if len(parity_sample_ids) != PARITY_SAMPLE_COUNT or len(set(parity_sample_ids)) != (
        PARITY_SAMPLE_COUNT
    ):
        raise DataIntegrityError("ONNX parity must use eight unique frozen sample identifiers")
    for label, digest in (
        ("model_sha256", model_sha256),
        ("parity_input_sha256", parity_input_sha256),
    ):
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise DataIntegrityError(f"{label} is not a lowercase SHA-256 digest")
    model_version = (
        f"plategauge/{artifact.protocol_id[:12]}/{artifact.hashes['checkpoint_sha256'][:12]}"
    )
    core: dict[str, Any] = {
        "schema_version": EXPORT_EVIDENCE_SCHEMA_VERSION,
        "kind": "frozen_final_onnx_export",
        "status": "passed",
        "model_version": model_version,
        "model_identity": artifact.evidence_identity(),
        "dataset_verification": dict(dataset_verification),
        "onnx": {
            "filename": model_filename,
            "sha256": model_sha256,
            "model_bytes": model_bytes,
            "maximum_allowed_bytes": MAXIMUM_FP32_MODEL_BYTES,
            "opset_version": 18,
            "precision": "FP32",
            "inputs": {
                "before": ["batch", 3, 224, 224],
                "after": ["batch", 3, 224, 224],
            },
            "output": {"quantiles": ["batch", 3], "order": ["q05", "q50", "q95"]},
        },
        "parity": {
            "sample_count": PARITY_SAMPLE_COUNT,
            "sample_ids": parity_sample_ids,
            "input_tensor_sha256": parity_input_sha256,
            "maximum_absolute_drift": maximum_parity_drift,
            "maximum_allowed_drift": MAXIMUM_ONNX_DRIFT,
            "passed": True,
        },
        "export_metadata": dict(export_metadata),
        "implicit_downloads_allowed": False,
    }
    return core | {"evidence_sha256": canonical_json_sha256(core)}


def _copy_exclusive(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
    except FileExistsError as exc:
        raise DataIntegrityError(f"Immutable ONNX artifact already exists: {destination}") from exc


def export_frozen_onnx_with_evidence(
    *,
    artifact: FrozenFinalArtifact,
    model: Any,
    dataset_root: str | Path,
    dataset_verification: Mapping[str, Any],
    output_path: str | Path,
    evidence_path: str | Path,
    exporter: Exporter = export_paired_onnx,
    parity_checker: ParityChecker = onnx_parity,
) -> dict[str, Any]:
    """Export through a temporary path; publish only after every gate passes."""

    output = Path(output_path)
    evidence_output = Path(evidence_path)
    if output.exists() or evidence_output.exists():
        existing = output if output.exists() else evidence_output
        raise DataIntegrityError(f"Immutable release artifact already exists: {existing}")
    sample_ids, before, after = _parity_inputs(artifact, dataset_root)
    model_version = (
        f"plategauge/{artifact.protocol_id[:12]}/{artifact.hashes['checkpoint_sha256'][:12]}"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="plategauge-onnx-", dir=output.parent) as temporary:
        temporary_model = Path(temporary) / "plategauge.onnx"
        metadata = exporter(
            model,
            temporary_model,
            model_version=model_version,
            opset_version=18,
            dynamic_batch=True,
        )
        if not temporary_model.is_file():
            raise DataIntegrityError("ONNX exporter did not create its declared artifact")
        model_bytes = temporary_model.stat().st_size
        model_sha = sha256_file(temporary_model)
        if metadata.get("onnx_sha256") != model_sha:
            raise DataIntegrityError("ONNX exporter metadata hash differs from model bytes")
        drift = float(parity_checker(model, temporary_model, before, after))
        payload = compose_export_evidence(
            artifact=artifact,
            dataset_verification=dataset_verification,
            model_filename=output.name,
            model_sha256=model_sha,
            model_bytes=model_bytes,
            export_metadata=metadata,
            parity_sample_ids=sample_ids,
            parity_input_sha256=_array_pair_sha256(before, after),
            maximum_parity_drift=drift,
        )
        _copy_exclusive(temporary_model, output)
    if sha256_file(output) != payload["onnx"]["sha256"]:
        output.unlink(missing_ok=True)
        raise DataIntegrityError("Published ONNX bytes changed during the exclusive copy")
    try:
        write_immutable_json(evidence_output, payload)
    except Exception:
        # This output was created by this call and has not been published with
        # evidence. Remove only that known partial artifact.
        output.unlink(missing_ok=True)
        raise
    return payload
