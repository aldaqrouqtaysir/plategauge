"""Fail-closed aggregation of immutable confirmatory outer-fold artifacts.

This module does not load a model or create predictions.  It reconstructs the
approved outer-task matrix from the inner-only selections, verifies the task
and artifact identities, then computes the preregistered reports from the
frozen CSV files.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import numpy as np

from .data import sha256_file
from .errors import DataIntegrityError
from .evaluation import PredictionRecord, read_predictions
from .folds import EXPECTED_FOLD_COUNTS, EXPECTED_VALID_COUNTS
from .metrics import (
    category_bootstrap_mae_difference,
    holm_adjust,
    metrics_by_slice,
    paired_sign_flip_pvalue,
    regression_metrics,
    target_slice_labels,
)
from .orchestration import (
    OUTER_WORKLOADS,
    POINT_OUTER_WORKLOADS,
    PRIMARY_WORKLOAD,
    ExperimentTask,
    TaskRequest,
    WorkloadResult,
    build_outer_tasks,
    protocol_preflight,
)
from .schema import ManifestRecord, read_manifest
from .uncertainty import evaluate_abstention_gate, evaluate_interval_gate

REPORT_SCHEMA_VERSION = 1
BOOTSTRAP_REPLICATES = 10_000
SIGN_FLIP_REPLICATES = 100_000
CONFIRMATORY_SEED = 20260919
NON_NEURAL_BASELINES = ("training_median", "handcrafted_ridge")


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"Non-finite JSON constant is forbidden: {value}")


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise DataIntegrityError(f"Required JSON artifact is not a regular file: {path}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DataIntegrityError(f"Cannot read strict JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DataIntegrityError(f"JSON root must be an object: {path}")
    return value


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DataIntegrityError(f"Value is not canonical JSON: {exc}") from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _safe_relative(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise DataIntegrityError("Artifact path must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise DataIntegrityError(f"Artifact path is unsafe: {value!r}")
    return path


def _immutable_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a report once, accepting only a semantically identical resume."""

    if path.exists():
        if _canonical_bytes(_read_json_object(path)) != _canonical_bytes(dict(payload)):
            raise DataIntegrityError(f"Refusing to overwrite different frozen report: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        if path.exists():
            raise DataIntegrityError(f"Frozen report appeared concurrently: {path}")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class _RecordedRunner:
    """Read-only runner identity used to reconstruct inner-only selections."""

    def __init__(self, fingerprint: str) -> None:
        if not fingerprint:
            raise DataIntegrityError("Run descriptor has an empty runner fingerprint")
        self._fingerprint = fingerprint

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def execute(self, request: TaskRequest, workspace: Path) -> WorkloadResult:
        del request, workspace
        raise DataIntegrityError("Post-evaluation is read-only and cannot execute workloads")


@dataclass(frozen=True, slots=True)
class EfficiencyEvidence:
    """Hash-bound export evidence needed for the complete efficiency gate."""

    model_path: Path
    model_sha256: str
    model_size_bytes: int
    maximum_pytorch_onnx_drift: float
    evidence_path: Path
    evidence_sha256: str
    protocol_id: str | None = None
    run_id: str | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> EfficiencyEvidence:
        evidence_path = Path(path)
        payload = _read_json_object(evidence_path)
        if payload.get("kind") == "frozen_final_onnx_export":
            return cls._from_export_evidence(evidence_path, payload)
        expected_keys = {
            "schema_version",
            "model_path",
            "model_sha256",
            "model_size_bytes",
            "maximum_pytorch_onnx_drift",
        }
        if set(payload) != expected_keys or payload["schema_version"] != "1.0":
            raise DataIntegrityError("Efficiency evidence fields differ from schema 1.0")
        model_path_value = payload["model_path"]
        if not isinstance(model_path_value, str) or not model_path_value:
            raise DataIntegrityError("Efficiency evidence model_path must be non-empty")
        model_path = Path(model_path_value)
        if not model_path.is_absolute():
            model_path = (evidence_path.parent / model_path).resolve()
        if not model_path.is_file() or model_path.is_symlink():
            raise DataIntegrityError("Efficiency evidence model is not a regular file")
        expected_digest = payload["model_sha256"]
        expected_size = payload["model_size_bytes"]
        drift = payload["maximum_pytorch_onnx_drift"]
        if not isinstance(expected_digest, str) or len(expected_digest) != 64:
            raise DataIntegrityError("Efficiency model SHA-256 is malformed")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 1
            or model_path.stat().st_size != expected_size
            or sha256_file(model_path) != expected_digest
        ):
            raise DataIntegrityError("Efficiency model size/hash does not match its evidence")
        if (
            not isinstance(drift, (int, float))
            or isinstance(drift, bool)
            or not math.isfinite(float(drift))
            or float(drift) < 0
        ):
            raise DataIntegrityError("Efficiency parity drift must be finite and non-negative")
        return cls(
            model_path=model_path,
            model_sha256=expected_digest,
            model_size_bytes=expected_size,
            maximum_pytorch_onnx_drift=float(drift),
            evidence_path=evidence_path.resolve(),
            evidence_sha256=sha256_file(evidence_path),
        )

    @classmethod
    def _from_export_evidence(
        cls, evidence_path: Path, payload: dict[str, Any]
    ) -> EfficiencyEvidence:
        """Load the canonical nested sidecar emitted by the frozen exporter."""

        expected_keys = {
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
        if (
            set(payload) != expected_keys
            or payload.get("schema_version") != "1.0"
            or payload.get("status") != "passed"
            or payload.get("implicit_downloads_allowed") is not False
        ):
            raise DataIntegrityError("Frozen ONNX export evidence differs from schema 1.0")
        embedded_digest = payload.get("evidence_sha256")
        core = {key: value for key, value in payload.items() if key != "evidence_sha256"}
        if (
            not isinstance(embedded_digest, str)
            or embedded_digest != _canonical_sha256(core)
        ):
            raise DataIntegrityError("Frozen ONNX export evidence hash is invalid")

        onnx = payload.get("onnx")
        parity = payload.get("parity")
        identity = payload.get("model_identity")
        if not isinstance(onnx, dict) or not isinstance(parity, dict):
            raise DataIntegrityError("Frozen ONNX export evidence sections are malformed")
        if not isinstance(identity, dict):
            raise DataIntegrityError("Frozen ONNX export model identity is malformed")
        model_path = (evidence_path.parent / _safe_relative(onnx.get("filename"))).resolve()
        if not model_path.is_file() or model_path.is_symlink():
            raise DataIntegrityError("Efficiency evidence model is not a regular file")
        expected_digest = onnx.get("sha256")
        expected_size = onnx.get("model_bytes")
        drift = parity.get("maximum_absolute_drift")
        if not isinstance(expected_digest, str) or len(expected_digest) != 64:
            raise DataIntegrityError("Efficiency model SHA-256 is malformed")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 1
            or model_path.stat().st_size != expected_size
            or sha256_file(model_path) != expected_digest
        ):
            raise DataIntegrityError("Efficiency model size/hash does not match its evidence")
        if (
            parity.get("passed") is not True
            or not isinstance(drift, (int, float))
            or isinstance(drift, bool)
            or not math.isfinite(float(drift))
            or float(drift) < 0
        ):
            raise DataIntegrityError("Efficiency parity drift must be finite and passed")
        protocol_id = identity.get("protocol_id")
        run_id = identity.get("run_id")
        if not isinstance(protocol_id, str) or len(protocol_id) != 64:
            raise DataIntegrityError("Frozen ONNX export protocol identity is malformed")
        if not isinstance(run_id, str) or len(run_id) != 64:
            raise DataIntegrityError("Frozen ONNX export run identity is malformed")
        return cls(
            model_path=model_path,
            model_sha256=expected_digest,
            model_size_bytes=expected_size,
            maximum_pytorch_onnx_drift=float(drift),
            evidence_path=evidence_path.resolve(),
            evidence_sha256=sha256_file(evidence_path),
            protocol_id=protocol_id,
            run_id=run_id,
        )


@dataclass(frozen=True, slots=True)
class _LoadedOuter:
    task: ExperimentTask
    payload: dict[str, Any]
    predictions: tuple[PredictionRecord, ...]
    result_path: Path
    prediction_path: Path


def _validate_run_descriptor(
    run_path: Path, *, protocol_id: str, manifest_path: Path, record_count: int
) -> dict[str, Any]:
    run = _read_json_object(run_path)
    run_id = run.get("run_id")
    core = {key: value for key, value in run.items() if key != "run_id"}
    if not isinstance(run_id, str) or run_id != _canonical_sha256(core):
        raise DataIntegrityError("run.json run_id does not match its canonical descriptor")
    if run.get("schema_version") != "1.0":
        raise DataIntegrityError("run.json schema_version must equal '1.0'")
    protocol = run.get("protocol")
    if not isinstance(protocol, dict) or protocol.get("protocol_id") != protocol_id:
        raise DataIntegrityError("run.json protocol identity differs from current frozen inputs")
    inputs = protocol.get("input_hashes")
    if not isinstance(inputs, dict) or inputs.get("manifest") != sha256_file(manifest_path):
        raise DataIntegrityError("run.json is not bound to the supplied manifest")
    dataset = run.get("dataset_verification")
    if (
        not isinstance(dataset, dict)
        or dataset.get("manifest_sha256") != sha256_file(manifest_path)
        or dataset.get("record_count") != record_count
    ):
        raise DataIntegrityError("run.json dataset verification differs from the manifest")
    if not isinstance(run.get("runner_fingerprint"), str):
        raise DataIntegrityError("run.json runner_fingerprint is malformed")
    return run


def _expected_configuration(task: ExperimentTask) -> str:
    value = task.parameters.get("configuration", "")
    if not isinstance(value, str):
        raise DataIntegrityError(f"Task configuration is malformed: {task.task_id}")
    return value


def _expected_epoch(task: ExperimentTask) -> int:
    value = task.parameters.get("epoch", 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DataIntegrityError(f"Task epoch is malformed: {task.task_id}")
    return value


def _prediction_artifact(
    task_directory: Path,
    task: ExperimentTask,
    result: Mapping[str, Any],
) -> tuple[Path, list[dict[str, Any]]]:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        raise DataIntegrityError(f"Task has no artifact inventory: {task.task_id}")
    required = set(task.required_artifact_roles)
    roles: set[str] = set()
    paths: set[Path] = set()
    prediction: Path | None = None
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"role", "path", "size_bytes", "sha256"}:
            raise DataIntegrityError(f"Malformed artifact inventory: {task.task_id}")
        role = item["role"]
        if not isinstance(role, str) or role in roles:
            raise DataIntegrityError(f"Duplicate/malformed artifact role: {task.task_id}")
        relative = _safe_relative(item["path"])
        if relative in paths:
            raise DataIntegrityError(f"Duplicate artifact path: {task.task_id}")
        path = task_directory / relative
        if not path.is_file() or path.is_symlink():
            raise DataIntegrityError(f"Task artifact is missing: {path}")
        try:
            path.resolve().relative_to(task_directory.resolve())
        except ValueError as exc:
            raise DataIntegrityError(f"Task artifact escapes its directory: {path}") from exc
        size = item["size_bytes"]
        digest = item["sha256"]
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size != path.stat().st_size
            or not isinstance(digest, str)
            or digest != sha256_file(path)
        ):
            raise DataIntegrityError(f"Task artifact hash/size mismatch: {path}")
        roles.add(role)
        paths.add(relative)
        if role == "predictions":
            prediction = path
    if roles != required or prediction is None:
        raise DataIntegrityError(f"Task artifact roles differ from protocol: {task.task_id}")
    actual_files = {
        candidate.relative_to(task_directory)
        for candidate in (task_directory / "workload").rglob("*")
        if candidate.is_file()
    }
    if actual_files != paths:
        raise DataIntegrityError(f"Undeclared/missing task files: {task.task_id}")
    return prediction, artifacts


def _validate_outer_predictions(
    task: ExperimentTask,
    payload: Mapping[str, Any],
    records: Sequence[PredictionRecord],
    manifest_by_id: Mapping[str, ManifestRecord],
) -> None:
    if task.evaluation_fold is None:
        raise DataIntegrityError(f"Outer task lacks an evaluation fold: {task.task_id}")
    expected_ids = sorted(
        sample_id
        for sample_id, record in manifest_by_id.items()
        if record.outer_fold == task.evaluation_fold
    )
    observed_ids = [record.sample_id for record in records]
    if observed_ids != expected_ids or len(observed_ids) != len(set(observed_ids)):
        raise DataIntegrityError(f"Outer predictions do not cover the fold exactly: {task.task_id}")
    configuration = _expected_configuration(task)
    epoch = _expected_epoch(task)
    for prediction in records:
        source = manifest_by_id[prediction.sample_id]
        if (
            prediction.category != source.category
            or prediction.outer_fold != source.outer_fold
            or not math.isclose(
                prediction.target, source.leftover_fraction, rel_tol=0.0, abs_tol=1e-12
            )
            or prediction.workload != task.workload
            or prediction.configuration != configuration
            or prediction.epoch != epoch
        ):
            raise DataIntegrityError(
                f"Prediction metadata differs from the frozen task: {prediction.sample_id}"
            )
        if task.workload in POINT_OUTER_WORKLOADS and not (
            prediction.q05 == prediction.q50 == prediction.q95
        ):
            raise DataIntegrityError(f"Point baseline emitted a non-point interval: {task.task_id}")
    for name, expected in task.expected_counts.items():
        if payload.get(name) != expected:
            raise DataIntegrityError(f"Task payload {name} differs from protocol: {task.task_id}")
    targets = np.asarray([record.target for record in records])
    predictions = np.asarray([record.q50 for record in records])
    categories = np.asarray([record.category for record in records])
    calculated = regression_metrics(targets, predictions, categories).macro_category_mae
    reported = payload.get("macro_category_mae")
    if (
        not isinstance(reported, (int, float))
        or isinstance(reported, bool)
        or not math.isclose(calculated, float(reported), rel_tol=1e-12, abs_tol=1e-12)
    ):
        raise DataIntegrityError(f"Task payload metric differs from predictions: {task.task_id}")
    if task.workload == PRIMARY_WORKLOAD:
        policy = task.parameters.get("uncertainty_policy")
        if not isinstance(policy, dict):
            raise DataIntegrityError("Primary outer task lacks its inner-only uncertainty policy")
        threshold = policy.get("abstention_threshold")
        correction = policy.get("interval_correction")
        if (
            not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not isinstance(correction, (int, float))
            or isinstance(correction, bool)
            or payload.get("abstention_threshold") != threshold
            or payload.get("interval_correction") != correction
        ):
            raise DataIntegrityError("Primary uncertainty payload differs from inner-only policy")
        retained = sorted(
            record.sample_id
            for record in records
            if record.q95 - record.q05 <= float(threshold) + 1e-12
        )
        if payload.get("retained_sample_ids") != retained or payload.get("retained_count") != len(
            retained
        ):
            raise DataIntegrityError("Primary retained IDs differ from the frozen width rule")


def _load_outer_task(
    run_directory: Path,
    task: ExperimentTask,
    *,
    protocol_id: str,
    runner_fingerprint: str,
    manifest_by_id: Mapping[str, ManifestRecord],
) -> _LoadedOuter:
    directory = run_directory / "tasks" / task.task_id
    task_path = directory / "task.json"
    result_path = directory / "result.json"
    spec = _read_json_object(task_path)
    expected_spec = task.to_dict()
    if _canonical_bytes(spec) != _canonical_bytes(expected_spec):
        raise DataIntegrityError(f"Outer task specification is stale/tampered: {task.task_id}")
    result = _read_json_object(result_path)
    expected_result_keys = {
        "schema_version",
        "status",
        "task_id",
        "protocol_id",
        "task_spec_sha256",
        "runner_fingerprint",
        "payload",
        "payload_sha256",
        "artifacts",
    }
    if set(result) != expected_result_keys:
        raise DataIntegrityError(f"Outer result fields differ from schema: {task.task_id}")
    expected_identity = {
        "schema_version": "1.0",
        "status": "complete",
        "task_id": task.task_id,
        "protocol_id": protocol_id,
        "task_spec_sha256": _canonical_sha256(expected_spec),
        "runner_fingerprint": runner_fingerprint,
    }
    if any(result.get(key) != value for key, value in expected_identity.items()):
        raise DataIntegrityError(f"Outer result identity mismatch: {task.task_id}")
    payload = result.get("payload")
    if not isinstance(payload, dict) or result.get("payload_sha256") != _canonical_sha256(payload):
        raise DataIntegrityError(f"Outer result payload hash mismatch: {task.task_id}")
    prediction_path, _ = _prediction_artifact(directory, task, result)
    predictions = tuple(read_predictions(prediction_path))
    _validate_outer_predictions(task, payload, predictions, manifest_by_id)
    return _LoadedOuter(task, payload, predictions, result_path, prediction_path)


def _rank_quintiles(values: np.ndarray, sample_ids: Sequence[str]) -> np.ndarray:
    if len(values) != len(sample_ids) or len(values) < 5 or not np.isfinite(values).all():
        raise DataIntegrityError("Quintile slices require at least five aligned finite values")
    order = sorted(range(len(values)), key=lambda index: (float(values[index]), sample_ids[index]))
    labels = np.empty(len(values), dtype=object)
    for rank, index in enumerate(order):
        labels[index] = f"Q{min(5, rank * 5 // len(values) + 1)}"
    return labels.astype(str)


def _slice_metrics(
    predictions: Sequence[PredictionRecord], manifest_by_id: Mapping[str, ManifestRecord]
) -> dict[str, Any]:
    targets = np.asarray([record.target for record in predictions])
    values = np.asarray([record.q50 for record in predictions])
    categories = np.asarray([record.category for record in predictions])
    ids = [record.sample_id for record in predictions]
    masses = np.asarray([manifest_by_id[sample_id].before_mass_g for sample_id in ids])
    observers = np.asarray([manifest_by_id[sample_id].observer_score for sample_id in ids])
    supports = Counter(record.category for record in manifest_by_id.values())
    support_labels = np.asarray([f"n={supports[category]}" for category in categories])
    observer_labels = np.asarray([f"score={value}" for value in observers])
    result: dict[str, Any] = {
        "target_range": metrics_by_slice(
            targets, values, categories, target_slice_labels(targets)
        ),
        "category_support": metrics_by_slice(
            targets, values, categories, support_labels
        ),
        "before_mass_quintile": metrics_by_slice(
            targets, values, categories, _rank_quintiles(masses, ids)
        ),
        "observer_level": metrics_by_slice(
            targets, values, categories, observer_labels
        ),
    }
    return result


def _per_category_metrics(predictions: Sequence[PredictionRecord]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for category in sorted({record.category for record in predictions}):
        selected = [record for record in predictions if record.category == category]
        result[category] = regression_metrics(
            [record.target for record in selected],
            [record.q50 for record in selected],
            [record.category for record in selected],
        ).to_dict()
    return result


def _category_differences(
    primary: Sequence[PredictionRecord], comparator: Sequence[PredictionRecord]
) -> np.ndarray:
    primary_by_id = {record.sample_id: record for record in primary}
    comparator_by_id = {record.sample_id: record for record in comparator}
    if set(primary_by_id) != set(comparator_by_id):
        raise DataIntegrityError("Comparison workloads do not cover identical sample IDs")
    values: list[float] = []
    for category in sorted({record.category for record in primary}):
        ids = [record.sample_id for record in primary if record.category == category]
        values.append(
            float(
                np.mean(
                    [
                        abs(primary_by_id[sample_id].q50 - primary_by_id[sample_id].target)
                        - abs(
                            comparator_by_id[sample_id].q50
                            - comparator_by_id[sample_id].target
                        )
                        for sample_id in ids
                    ]
                )
            )
        )
    return np.asarray(values)


def _comparison_payload(
    primary: Sequence[PredictionRecord],
    comparator: Sequence[PredictionRecord],
    *,
    comparator_name: str,
) -> dict[str, Any]:
    targets = np.asarray([record.target for record in primary])
    primary_values = np.asarray([record.q50 for record in primary])
    comparator_by_id = {record.sample_id: record for record in comparator}
    comparator_values = np.asarray(
        [comparator_by_id[record.sample_id].q50 for record in primary]
    )
    categories = np.asarray([record.category for record in primary])
    bootstrap = category_bootstrap_mae_difference(
        targets,
        primary_values,
        comparator_values,
        categories,
        replicates=BOOTSTRAP_REPLICATES,
        seed=CONFIRMATORY_SEED,
    ).to_dict()
    primary_mae = regression_metrics(targets, primary_values, categories).macro_category_mae
    comparator_mae = regression_metrics(
        targets, comparator_values, categories
    ).macro_category_mae
    relative_improvement = (
        (comparator_mae - primary_mae) / comparator_mae if comparator_mae > 0 else None
    )
    return {
        "comparator": comparator_name,
        "primary_macro_category_mae": primary_mae,
        "comparator_macro_category_mae": comparator_mae,
        "relative_improvement": relative_improvement,
        "bootstrap": bootstrap,
        "category_mae_differences_primary_minus_comparator": _category_differences(
            primary, comparator
        ).tolist(),
    }


def _decisions(
    workloads: Mapping[str, Mapping[str, Any]],
    comparisons: Mapping[str, Mapping[str, Any]],
    *,
    efficiency_evidence: EfficiencyEvidence | None,
) -> dict[str, Any]:
    primary_mae = float(workloads[PRIMARY_WORKLOAD]["overall"]["macro_category_mae"])
    p90 = float(workloads[PRIMARY_WORKLOAD]["overall"]["p90_absolute_error"])
    target_slices = workloads[PRIMARY_WORKLOAD]["slices"]["target_range"]
    worst_target_mae = max(float(value["micro_mae"]) for value in target_slices.values())
    after_improvement = comparisons["after_only"]["relative_improvement"]
    non_neural_improvement = comparisons["best_non_neural"]["relative_improvement"]
    paired_value = bool(
        after_improvement is not None
        and float(after_improvement) >= 0.05
        and non_neural_improvement is not None
        and float(non_neural_improvement) >= 0.10
    )
    superiority = all(
        float(comparisons[name]["bootstrap"]["upper_95"]) < 0.0
        for name in ("after_only", "best_non_neural")
    )
    numeric_demo = primary_mae <= 0.10 and p90 <= 0.25 and worst_target_mae <= 0.15
    median_mae = float(workloads["training_median"]["overall"]["macro_category_mae"])
    ridge_mae = float(workloads["handcrafted_ridge"]["overall"]["macro_category_mae"])
    fails_both_non_neural = primary_mae >= median_mae and primary_mae >= ridge_mae
    stop = primary_mae > 0.20 or fails_both_non_neural
    if stop:
        recommendation = "project_stop"
    elif 0.15 < primary_mae <= 0.20:
        recommendation = "negative_research_record"
    elif (
        not numeric_demo
        or not paired_value
        or not superiority
    ):
        recommendation = "benchmark_failure_explorer"
    else:
        recommendation = "numeric_estimator_candidate"

    dino_mae = float(workloads["frozen_paired_dinov2"]["overall"]["macro_category_mae"])
    accuracy_gap = primary_mae - dino_mae
    efficiency: dict[str, Any] = {
        "mobilenet_minus_dinov2_macro_category_mae": accuracy_gap,
        "accuracy_reference_passed": accuracy_gap <= 0.02,
        "model_size_bytes": None,
        "model_size_passed": None,
        "maximum_pytorch_onnx_drift": None,
        "parity_passed": None,
        "passed": None,
        "missing_evidence": ["hash-bound exported model size", "PyTorch/ONNX parity drift"],
    }
    if efficiency_evidence is not None:
        size_passed = efficiency_evidence.model_size_bytes <= 15_000_000
        parity_passed = efficiency_evidence.maximum_pytorch_onnx_drift <= 1e-4
        efficiency |= {
            "model_size_bytes": efficiency_evidence.model_size_bytes,
            "model_size_passed": size_passed,
            "maximum_pytorch_onnx_drift": efficiency_evidence.maximum_pytorch_onnx_drift,
            "parity_passed": parity_passed,
            "passed": accuracy_gap <= 0.02 and size_passed and parity_passed,
            "missing_evidence": [],
            "model_sha256": efficiency_evidence.model_sha256,
            "evidence_sha256": efficiency_evidence.evidence_sha256,
        }
    return {
        "paired_value": {
            "passed": paired_value,
            "after_only_relative_improvement": after_improvement,
            "best_non_neural_relative_improvement": non_neural_improvement,
            "required_relative_improvements": {"after_only": 0.05, "best_non_neural": 0.10},
        },
        "superiority_wording": {
            "passed": superiority,
            "rule": "both paired category-bootstrap upper bounds are below zero",
        },
        "numeric_demo": {
            "passed": numeric_demo,
            "macro_category_mae": primary_mae,
            "p90_absolute_error": p90,
            "worst_broad_target_slice_micro_mae": worst_target_mae,
        },
        "efficiency": efficiency,
        "stop": {
            "triggered": stop,
            "macro_mae_above_0_20": primary_mae > 0.20,
            "failed_to_beat_median_and_handcrafted": fails_both_non_neural,
        },
        "release_recommendation": recommendation,
        "benchmark_only": recommendation == "benchmark_failure_explorer",
    }


def build_frozen_reports(
    *,
    run_directory: str | Path,
    manifest_path: str | Path,
    audit_report_path: str | Path,
    config_path: str | Path,
    folds_path: str | Path,
    results_path: str | Path,
    bootstrap_path: str | Path,
    efficiency_evidence_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate all immutable outer artifacts and emit the two frozen reports."""

    run_dir = Path(run_directory)
    manifest_file = Path(manifest_path)
    records = read_manifest(manifest_file)
    valid = [record for record in records if record.is_valid]
    observed_counts = dict(sorted(Counter(record.category for record in valid).items()))
    if observed_counts != EXPECTED_VALID_COUNTS:
        raise DataIntegrityError("Valid manifest category counts differ from the frozen protocol")
    if dict(sorted(Counter(record.outer_fold for record in valid).items())) != EXPECTED_FOLD_COUNTS:
        raise DataIntegrityError("Valid manifest outer-fold labels differ from the frozen protocol")
    preflight, protocol = protocol_preflight(
        audit_report_path=audit_report_path,
        manifest_path=manifest_file,
        config_path=config_path,
        folds_path=folds_path,
    )
    if preflight.status != "ready" or protocol is None:
        raise DataIntegrityError(f"Frozen protocol preflight is blocked: {preflight.blocker}")
    run = _validate_run_descriptor(
        run_dir / "run.json",
        protocol_id=protocol.protocol_id,
        manifest_path=manifest_file,
        record_count=len(records),
    )
    runner_fingerprint = str(run["runner_fingerprint"])
    runner = _RecordedRunner(runner_fingerprint)
    tasks = build_outer_tasks(protocol, run_dir, runner)
    expected_task_ids = {
        f"outer.fold-{fold}.{workload}"
        for fold in range(5)
        for workload in OUTER_WORKLOADS
    }
    if {task.task_id for task in tasks} != expected_task_ids or len(tasks) != 40:
        raise DataIntegrityError("Reconstructed outer task matrix is incomplete")
    task_root = run_dir / "tasks"
    observed_outer_dirs = {
        path.name
        for path in task_root.glob("outer.fold-*")
        if path.is_dir() and not path.is_symlink()
    }
    if observed_outer_dirs != expected_task_ids:
        raise DataIntegrityError("Outer task directories differ from the exact 40-task matrix")

    manifest_by_id = {record.sample_id: record for record in valid}
    loaded = [
        _load_outer_task(
            run_dir,
            task,
            protocol_id=protocol.protocol_id,
            runner_fingerprint=runner_fingerprint,
            manifest_by_id=manifest_by_id,
        )
        for task in tasks
    ]
    predictions_by_workload: dict[str, list[PredictionRecord]] = {
        workload: [] for workload in OUTER_WORKLOADS
    }
    for item in loaded:
        predictions_by_workload[item.task.workload].extend(item.predictions)
    expected_ids = set(manifest_by_id)
    for workload, predictions in predictions_by_workload.items():
        ids = [record.sample_id for record in predictions]
        if len(ids) != len(expected_ids) or len(set(ids)) != len(ids) or set(ids) != expected_ids:
            raise DataIntegrityError(
                f"Workload does not provide exactly one prediction per valid sample: {workload}"
            )
        predictions.sort(key=lambda record: record.sample_id)

    workload_results: dict[str, dict[str, Any]] = {}
    for workload in OUTER_WORKLOADS:
        predictions = predictions_by_workload[workload]
        targets = np.asarray([record.target for record in predictions])
        values = np.asarray([record.q50 for record in predictions])
        categories = np.asarray([record.category for record in predictions])
        slices = _slice_metrics(predictions, manifest_by_id)
        if workload == PRIMARY_WORKLOAD:
            widths = np.asarray([record.q95 - record.q05 for record in predictions])
            slices["confidence_width_quintile"] = metrics_by_slice(
                targets,
                values,
                categories,
                _rank_quintiles(widths, [record.sample_id for record in predictions]),
            )
        workload_results[workload] = {
            "overall": regression_metrics(targets, values, categories).to_dict(),
            "slices": slices,
            "per_category": _per_category_metrics(predictions),
        }

    primary = predictions_by_workload[PRIMARY_WORKLOAD]
    non_neural = min(
        NON_NEURAL_BASELINES,
        key=lambda name: (
            float(workload_results[name]["overall"]["macro_category_mae"]), name
        ),
    )
    comparisons = {
        "after_only": _comparison_payload(
            primary,
            predictions_by_workload["after_only_mobilenet"],
            comparator_name="after_only_mobilenet",
        ),
        "best_non_neural": _comparison_payload(
            primary,
            predictions_by_workload[non_neural],
            comparator_name=non_neural,
        ),
    }
    raw_pvalues = [
        paired_sign_flip_pvalue(
            np.asarray(comparisons[name]["category_mae_differences_primary_minus_comparator"]),
            replicates=SIGN_FLIP_REPLICATES,
            seed=CONFIRMATORY_SEED,
        )
        for name in ("after_only", "best_non_neural")
    ]
    adjusted = holm_adjust(raw_pvalues)
    for index, name in enumerate(("after_only", "best_non_neural")):
        comparisons[name]["sign_flip"] = {
            "two_sided_monte_carlo_pvalue": raw_pvalues[index],
            "holm_adjusted_pvalue": adjusted[index],
            "replicates": SIGN_FLIP_REPLICATES,
            "seed": CONFIRMATORY_SEED,
        }

    primary_targets = np.asarray([record.target for record in primary])
    primary_values = np.asarray([record.q50 for record in primary])
    primary_categories = np.asarray([record.category for record in primary])
    primary_lower = np.asarray([record.q05 for record in primary])
    primary_upper = np.asarray([record.q95 for record in primary])
    retained_ids: set[str] = set()
    policies_by_fold: dict[str, dict[str, float]] = {}
    for item in loaded:
        if item.task.workload != PRIMARY_WORKLOAD:
            continue
        policy = item.task.parameters["uncertainty_policy"]
        fold = str(item.task.evaluation_fold)
        policies_by_fold[fold] = {
            "interval_correction": float(policy["interval_correction"]),
            "abstention_threshold": float(policy["abstention_threshold"]),
        }
        retained_ids.update(str(value) for value in item.payload["retained_sample_ids"])
    retained = np.asarray([record.sample_id in retained_ids for record in primary])
    interval_gate = evaluate_interval_gate(
        primary_targets, primary_lower, primary_upper
    ).to_dict()
    abstention_gate = evaluate_abstention_gate(
        primary_targets, primary_values, primary_categories, retained
    ).to_dict()
    uncertainty = {
        "workload": PRIMARY_WORKLOAD,
        "interval_label": "empirical benchmark interval",
        "formal_conformal_guarantee": False,
        "policies_by_outer_fold": policies_by_fold,
        "interval_gate": interval_gate,
        "abstention_gate": abstention_gate,
        "public_interval_allowed": interval_gate["passed"],
        "useful_abstention_claim_allowed": abstention_gate["passed"],
    }

    efficiency_evidence = (
        EfficiencyEvidence.from_file(efficiency_evidence_path)
        if efficiency_evidence_path is not None
        else None
    )
    if efficiency_evidence is not None:
        if (
            efficiency_evidence.protocol_id is not None
            and efficiency_evidence.protocol_id != protocol.protocol_id
        ):
            raise DataIntegrityError("Efficiency evidence uses a different frozen protocol")
        if (
            efficiency_evidence.run_id is not None
            and efficiency_evidence.run_id != run["run_id"]
        ):
            raise DataIntegrityError("Efficiency evidence uses a different experiment run")
    decisions = _decisions(
        workload_results,
        comparisons,
        efficiency_evidence=efficiency_evidence,
    )
    provenance_artifacts = [
        {
            "task_id": item.task.task_id,
            "result_sha256": sha256_file(item.result_path),
            "predictions_sha256": sha256_file(item.prediction_path),
        }
        for item in sorted(loaded, key=lambda value: value.task.task_id)
    ]
    bootstrap_report: dict[str, Any] = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "frozen": True,
        "run_id": run["run_id"],
        "protocol_id": protocol.protocol_id,
        "manifest_sha256": sha256_file(manifest_file),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "sign_flip_replicates": SIGN_FLIP_REPLICATES,
        "seed": CONFIRMATORY_SEED,
        "difference_direction": "paired_mobilenet_minus_comparator; negative favors paired",
        "comparisons": comparisons,
    }
    results_report: dict[str, Any] = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "frozen": True,
        "run_id": run["run_id"],
        "protocol_id": protocol.protocol_id,
        "manifest_sha256": sha256_file(manifest_file),
        "dataset": {
            "valid_pairs": len(valid),
            "categories": len(observed_counts),
            "fold_counts": {
                str(fold): count
                for fold, count in sorted(Counter(record.outer_fold for record in valid).items())
            },
        },
        "analysis": {
            "confirmatory_seed": CONFIRMATORY_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "sign_flip_replicates": SIGN_FLIP_REPLICATES,
            "quintile_method": "stable equal-frequency rank; sample_id breaks value ties",
            "best_non_neural_rule": "lowest aggregate macro-category MAE; workload name breaks ties",
            "analysis_code_sha256": sha256_file(Path(__file__)),
        },
        "workloads": workload_results,
        "comparisons": {
            name: {
                key: value
                for key, value in comparison.items()
                if key != "category_mae_differences_primary_minus_comparator"
            }
            for name, comparison in comparisons.items()
        },
        "uncertainty": uncertainty,
        "decisions": decisions,
        "provenance": {
            "run_descriptor_sha256": sha256_file(run_dir / "run.json"),
            "outer_artifacts": provenance_artifacts,
            "bootstrap_report_canonical_sha256": _canonical_sha256(bootstrap_report),
        },
    }
    _immutable_json_write(Path(bootstrap_path), bootstrap_report)
    _immutable_json_write(Path(results_path), results_report)
    return results_report, bootstrap_report
