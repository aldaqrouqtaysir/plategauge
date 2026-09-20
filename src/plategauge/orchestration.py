"""Fail-closed orchestration for the frozen PlateGauge experiment protocol.

The orchestrator owns information boundaries, task identity, immutable result
metadata, and resume validation. Workload implementations are deliberately
bound through :class:`TaskRunner`: the in-repository production runner executes
approved workloads, tests use tiny deterministic runners, and an external
command runner remains available for isolated workers. The orchestrator never
substitutes synthetic results for a missing production dependency or artifact.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shlex
import subprocess
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any, Protocol

import numpy as np

from .baselines import PAIRING_MAP_FIELDS, fixed_within_category_wrong_pairs
from .data import sha256_file
from .errors import DataIntegrityError
from .evaluation import PREDICTION_FIELDS
from .folds import EXPECTED_FOLD_COUNTS, FROZEN_CATEGORY_FOLDS, inner_folds
from .metrics import macro_category_mae
from .model import (
    MOBILENET_CHECKPOINT,
    MOBILENET_HF_REPOSITORY,
    MOBILENET_HF_REVISION,
    MOBILENET_WEIGHTS_FILENAME,
    MOBILENET_WEIGHTS_SHA256,
    MOBILENET_WEIGHTS_SIZE,
)
from .schema import ManifestRecord, read_manifest
from .training import (
    MODEL_CONFIGURATIONS,
    InnerRun,
    SelectedConfiguration,
    select_inner_configuration,
)
from .uncertainty import (
    correct_intervals,
    derive_abstention_threshold,
    interval_correction,
)

ORCHESTRATION_SCHEMA_VERSION = "1.0"
APPROVED_PROTOCOL_STATUS = "approved_for_execution"
DEFAULT_EXPERIMENT_CONFIG = Path("configs/experiment.toml")
DEFAULT_FOLDS_CONFIG = Path("configs/frozen_folds.json")
DEFAULT_RUN_DIRECTORY = Path("reports/experiments/confirmatory")

PRIMARY_WORKLOAD = "paired_mobilenet"
TUNED_WORKLOADS = ("handcrafted_ridge", "frozen_paired_dinov2")
UNCERTAINTY_OUTER_WORKLOADS = frozenset({PRIMARY_WORKLOAD})
POINT_OUTER_WORKLOADS = frozenset(
    {
        "training_median",
        "handcrafted_ridge",
        "frozen_paired_dinov2",
        "observer_score_context_only",
    }
)
OUTER_WORKLOADS = (
    PRIMARY_WORKLOAD,
    "training_median",
    "handcrafted_ridge",
    "paired_resnet50",
    "after_only_mobilenet",
    "frozen_paired_dinov2",
    "fixed_within_category_wrong_pair",
    "observer_score_context_only",
)

REFERENCE_ARTIFACTS: dict[str, dict[str, Any]] = {
    "paired_resnet50": {
        "checkpoint": "resnet50.a1_in1k",
        "repository": "timm/resnet50.a1_in1k",
        "revision": "93271f4677dbf7b4d7f7e7d9d7811bd66c327e56",
        "filename": "model.safetensors",
        "size_bytes": 102_469_840,
        "sha256": "773525d5821de224f8f30c33377b7a795d7863e08522698200d3217d3f2a41bb",
        "license": "Apache-2.0",
    },
    "frozen_paired_dinov2": {
        "checkpoint": "vit_small_patch14_dinov2.lvd142m",
        "repository": "timm/vit_small_patch14_dinov2.lvd142m",
        "revision": "4476dc0c66daca2ef4a40d2625b4a7063f02b685",
        "filename": "model.safetensors",
        "size_bytes": 88_240_510,
        "sha256": "04d27f3400d059fc0cfd7d17dd1909a75bf3ea8fb3eeb48b97cb99e57ee20081",
        "license": "Apache-2.0",
    },
}

APPROVED_EXPERIMENT_CONFIG: dict[str, Any] = {
    "schema_version": "1.0",
    "protocol_status": APPROVED_PROTOCOL_STATUS,
    "confirmatory_seed": 20260919,
    "stability_seeds": [20260920, 20260921],
    "maximum_total_gpu_hours": 10,
    "outer_folds": 5,
    "maximum_epochs": 80,
    "patience": 12,
    "freeze_encoder_epochs": 5,
    "batch_size": 32,
    "weight_decay": 0.0001,
    "gradient_clip": 1.0,
    "mixed_precision_on_cuda": True,
    "preprocessing": {
        "resize_shorter_edge": 256,
        "crop_size": 224,
        "normalization": "ImageNet mean/std",
    },
    "augmentation": {
        "horizontal_flip_probability": 0.5,
        "maximum_rotation_degrees": 8.0,
        "maximum_translation_fraction": 0.05,
        "minimum_scale": 0.95,
        "maximum_scale": 1.05,
        "brightness_jitter": 0.10,
        "contrast_jitter": 0.10,
        "vertical_flip": False,
        "shared_geometry": True,
        "independent_color_jitter": True,
    },
    "model": {
        "architecture": "shared_encoder_late_fusion_ordered_quantiles",
        "checkpoint": MOBILENET_CHECKPOINT,
        "pretrained_source": "timm/Hugging Face",
        "pretrained_repository": MOBILENET_HF_REPOSITORY,
        "pretrained_filename": MOBILENET_WEIGHTS_FILENAME,
        "pretrained_revision": MOBILENET_HF_REVISION,
        "pretrained_sha256": MOBILENET_WEIGHTS_SHA256,
        "pretrained_size_bytes": MOBILENET_WEIGHTS_SIZE,
        "feature_dimension": 1024,
        "fusion_dimension": 4096,
        "head_hidden_dimension": 256,
        "quantiles": [0.05, 0.50, 0.95],
        "interval_loss_weight": 0.5,
        "pin_gate": {
            "required_before_training": True,
            "reason": (
                "Training accepts only a local artifact matching the pinned revision's "
                "exact size and SHA-256."
            ),
        },
    },
    "configuration": {
        "M1": {
            "encoder_learning_rate": 0.00003,
            "head_learning_rate": 0.0003,
            "dropout": 0.2,
        },
        "M2": {
            "encoder_learning_rate": 0.0001,
            "head_learning_rate": 0.001,
            "dropout": 0.4,
        },
    },
    "ridge": {"alphas": [0.01, 0.1, 1.0, 10.0, 100.0]},
    "uncertainty": {
        "nominal_coverage": 0.90,
        "maximum_abstention_width": 0.30,
        "retention_quantile": 0.80,
    },
}


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise DataIntegrityError(f"Value is not canonical JSON: {exc}") from exc
    return serialized.encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataIntegrityError(f"Cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DataIntegrityError(f"JSON root must be an object: {path}")
    return value


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise DataIntegrityError(f"Refusing to overwrite immutable artifact: {path}")
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise DataIntegrityError(f"Artifact appeared during atomic write: {path}")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_or_validate_json(path: Path, payload: Mapping[str, Any]) -> bool:
    """Write an immutable JSON artifact, or verify an identical existing one.

    Returns ``True`` when written and ``False`` when a byte-equivalent semantic
    artifact already exists.
    """

    if path.exists():
        existing = _read_json_object(path)
        if _canonical_json_bytes(existing) != _canonical_json_bytes(dict(payload)):
            raise DataIntegrityError(f"Immutable artifact differs on resume: {path}")
        return False
    _atomic_write_json(path, payload)
    return True


@dataclass(frozen=True, slots=True)
class ProtocolPreflight:
    status: str
    blockers: tuple[str, ...]
    protocol_id: str | None
    input_hashes: dict[str, str]
    inner_primary_tasks: int = 40
    inner_tuning_tasks: int = 10
    outer_tasks: int = 40
    final_tasks: int = 1

    @property
    def blocker(self) -> str | None:
        return None if not self.blockers else "; ".join(self.blockers)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"blocker": self.blocker}


@dataclass(frozen=True, slots=True)
class FrozenProtocol:
    protocol_id: str
    confirmatory_seed: int
    ridge_alphas: tuple[float, ...]
    maximum_epochs: int
    patience: int
    config: dict[str, Any]
    input_paths: dict[str, str]
    input_hashes: dict[str, str]

    def public_descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": ORCHESTRATION_SCHEMA_VERSION,
            "protocol_id": self.protocol_id,
            "confirmatory_seed": self.confirmatory_seed,
            "ridge_alphas": list(self.ridge_alphas),
            "maximum_epochs": self.maximum_epochs,
            "patience": self.patience,
            "input_hashes": dict(sorted(self.input_hashes.items())),
        }


@dataclass(frozen=True, slots=True)
class ExperimentTask:
    task_id: str
    stage: str
    workload: str
    outer_fold: int | None
    training_folds: tuple[int, ...]
    validation_folds: tuple[int, ...]
    evaluation_fold: int | None
    parameters: dict[str, Any]
    expected_counts: dict[str, int]
    required_artifact_roles: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TaskRequest:
    schema_version: str
    protocol_id: str
    manifest_path: str
    dataset_root: str
    task: ExperimentTask

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "manifest_path": self.manifest_path,
            "dataset_root": self.dataset_root,
            "task": self.task.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class WorkloadResult:
    payload: dict[str, Any]
    artifacts: dict[str, str]


class TaskRunner(Protocol):
    @property
    def fingerprint(self) -> str: ...

    def execute(self, request: TaskRequest, workspace: Path) -> WorkloadResult: ...


@dataclass(frozen=True, slots=True)
class ExperimentRunSummary:
    status: str
    stage: str
    protocol_id: str
    run_id: str
    planned_tasks: int
    executed_tasks: int
    resumed_tasks: int
    selections_written: int
    output_directory: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_audit(audit: Mapping[str, Any], manifest_hash: str, blockers: list[str]) -> None:
    required_values: dict[str, Any] = {
        "schema_version": "1.0",
        "workbook_rows": 678,
        "matched_pairs": 524,
        "missing_image_rows": 154,
        "valid_pairs": 514,
        "invalid_mass_pairs": 10,
        "valid_categories": 34,
        "files_verified": True,
        "hashes_verified": True,
        "expected_counts_match": True,
        "cross_fold_duplicate_components": 0,
        "passed": True,
    }
    for name, expected in required_values.items():
        if audit.get(name) != expected:
            blockers.append(f"audit.{name} must equal {expected!r}, found {audit.get(name)!r}")
    expected_fold_counts = {str(key): value for key, value in EXPECTED_FOLD_COUNTS.items()}
    if audit.get("fold_counts") != expected_fold_counts:
        blockers.append("audit.fold_counts differ from the frozen protocol")
    issues = audit.get("issues")
    if not isinstance(issues, list):
        blockers.append("audit.issues must be a list")
    elif issues:
        blockers.extend(f"audit issue: {issue}" for issue in issues)
    if audit.get("manifest_sha256") != manifest_hash:
        blockers.append(
            "audit.manifest_sha256 must bind the approved audit to the exact manifest bytes"
        )


def _validate_folds(folds: Mapping[str, Any], blockers: list[str]) -> None:
    if folds.get("schema_version") != "1.0":
        blockers.append("frozen folds schema_version must be '1.0'")
    status = str(folds.get("status", "")).lower()
    if any(token in status for token in ("blocked", "pending", "unresolved")) or not any(
        token in status for token in ("approved", "frozen", "resolved")
    ):
        blockers.append("frozen folds status is not approved/resolved")
    expected = {
        str(fold): {"categories": list(categories), "expected_n": EXPECTED_FOLD_COUNTS[fold]}
        for fold, categories in FROZEN_CATEGORY_FOLDS.items()
    }
    if folds.get("folds") != expected:
        blockers.append("frozen fold assignments or counts differ from code constants")


def _configuration_values(configuration: Mapping[str, Any], name: str) -> dict[str, float]:
    value = configuration.get(name)
    if not isinstance(value, dict):
        raise DataIntegrityError(f"Missing configuration.{name}")
    try:
        return {
            "encoder_learning_rate": float(value["encoder_learning_rate"]),
            "head_learning_rate": float(value["head_learning_rate"]),
            "dropout": float(value["dropout"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise DataIntegrityError(f"Invalid configuration.{name}") from exc


def _validate_config(config: Mapping[str, Any], blockers: list[str]) -> None:
    def compare(actual: Any, expected: Any, path: str) -> None:
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                blockers.append(f"{path} must be a table")
                return
            if set(actual) != set(expected):
                blockers.append(
                    f"{path} keys differ from the approved locked protocol: "
                    f"expected={sorted(expected)!r}, found={sorted(actual)!r}"
                )
            for key in sorted(expected.keys() & actual.keys()):
                compare(actual[key], expected[key], f"{path}.{key}")
            return
        if isinstance(expected, list):
            if not isinstance(actual, list) or len(actual) != len(expected):
                blockers.append(f"{path} differs from the approved locked protocol")
                return
            for index, (actual_item, expected_item) in enumerate(
                zip(actual, expected, strict=True)
            ):
                compare(actual_item, expected_item, f"{path}[{index}]")
            return
        if type(actual) is not type(expected) or actual != expected:
            blockers.append(f"{path} must equal {expected!r}, found {actual!r}")

    compare(dict(config), APPROVED_EXPERIMENT_CONFIG, "config")


def protocol_preflight(
    *,
    audit_report_path: str | Path,
    manifest_path: str | Path,
    config_path: str | Path = DEFAULT_EXPERIMENT_CONFIG,
    folds_path: str | Path = DEFAULT_FOLDS_CONFIG,
) -> tuple[ProtocolPreflight, FrozenProtocol | None]:
    """Validate and fingerprint every outcome-independent protocol input."""

    paths = {
        "audit_report": Path(audit_report_path),
        "manifest": Path(manifest_path),
        "experiment_config": Path(config_path),
        "frozen_folds": Path(folds_path),
    }
    blockers: list[str] = []
    for name, path in paths.items():
        if not path.is_file():
            blockers.append(f"{name} is missing: {path}")
    if blockers:
        return ProtocolPreflight("blocked", tuple(blockers), None, {}), None

    input_hashes = {name: sha256_file(path) for name, path in paths.items()}
    audit = _read_json_object(paths["audit_report"])
    folds = _read_json_object(paths["frozen_folds"])
    try:
        config_value = tomllib.loads(paths["experiment_config"].read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DataIntegrityError(f"Cannot read experiment TOML: {exc}") from exc
    if not isinstance(config_value, dict):  # pragma: no cover - tomllib roots are dictionaries
        raise DataIntegrityError("Experiment TOML root must be a table")

    _validate_audit(audit, input_hashes["manifest"], blockers)
    _validate_folds(folds, blockers)
    _validate_config(config_value, blockers)
    if blockers:
        return ProtocolPreflight("blocked", tuple(blockers), None, input_hashes), None

    protocol_identity = {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "inputs": input_hashes,
        "confirmatory_seed": config_value["confirmatory_seed"],
        "approved_outer_workloads": list(OUTER_WORKLOADS),
        "reference_artifacts": REFERENCE_ARTIFACTS,
    }
    protocol_id = _canonical_sha256(protocol_identity)
    ridge = config_value["ridge"]
    protocol = FrozenProtocol(
        protocol_id=protocol_id,
        confirmatory_seed=int(config_value["confirmatory_seed"]),
        ridge_alphas=tuple(float(value) for value in ridge["alphas"]),
        maximum_epochs=int(config_value["maximum_epochs"]),
        patience=int(config_value["patience"]),
        config=config_value,
        input_paths={name: str(path.resolve()) for name, path in paths.items()},
        input_hashes=input_hashes,
    )
    return ProtocolPreflight("ready", (), protocol_id, input_hashes), protocol


def _fold_count(folds: Sequence[int]) -> int:
    return sum(EXPECTED_FOLD_COUNTS[fold] for fold in folds)


def _model_parameters(protocol: FrozenProtocol, configuration: str) -> dict[str, Any]:
    values = _configuration_values(protocol.config["configuration"], configuration)
    return {
        "configuration": configuration,
        **values,
        "maximum_epochs": protocol.maximum_epochs,
        "patience": protocol.patience,
        "freeze_encoder_epochs": int(protocol.config.get("freeze_encoder_epochs", 5)),
        "batch_size": int(protocol.config.get("batch_size", 32)),
        "weight_decay": float(protocol.config.get("weight_decay", 1e-4)),
        "gradient_clip": float(protocol.config.get("gradient_clip", 1.0)),
        "interval_loss_weight": float(protocol.config["model"].get("interval_loss_weight", 0.5)),
        "seed": protocol.confirmatory_seed,
        "selection_metric": "macro_category_mae",
        "input_size": 224,
        "pretrained_artifact": {
            "checkpoint": MOBILENET_CHECKPOINT,
            "repository": MOBILENET_HF_REPOSITORY,
            "revision": MOBILENET_HF_REVISION,
            "filename": MOBILENET_WEIGHTS_FILENAME,
            "size_bytes": MOBILENET_WEIGHTS_SIZE,
            "sha256": MOBILENET_WEIGHTS_SHA256,
            "license": "Apache-2.0",
        },
    }


def build_inner_tasks(protocol: FrozenProtocol) -> tuple[ExperimentTask, ...]:
    """Build primary M1/M2 tasks and inner-only Ridge-grid tuning tasks."""

    tasks: list[ExperimentTask] = []
    for outer_fold in sorted(FROZEN_CATEGORY_FOLDS):
        development_folds = inner_folds(outer_fold)
        for validation_fold in development_folds:
            training_folds = tuple(fold for fold in development_folds if fold != validation_fold)
            for configuration in ("M1", "M2"):
                tasks.append(
                    ExperimentTask(
                        task_id=(
                            f"inner.primary.outer-{outer_fold}.validation-{validation_fold}."
                            f"{configuration.lower()}"
                        ),
                        stage="inner_primary",
                        workload=PRIMARY_WORKLOAD,
                        outer_fold=outer_fold,
                        training_folds=training_folds,
                        validation_folds=(validation_fold,),
                        evaluation_fold=None,
                        parameters=_model_parameters(protocol, configuration),
                        expected_counts={
                            "training_count": _fold_count(training_folds),
                            "validation_count": EXPECTED_FOLD_COUNTS[validation_fold],
                        },
                        required_artifact_roles=("checkpoint", "validation_predictions"),
                    )
                )
        for workload in TUNED_WORKLOADS:
            parameters: dict[str, Any] = {
                "alphas": list(protocol.ridge_alphas),
                "selection_metric": "mean_inner_macro_category_mae",
                "tie_break": "smallest_alpha",
                "nested_validation_folds": list(development_folds),
                "seed": protocol.confirmatory_seed,
            }
            if workload == "frozen_paired_dinov2":
                parameters |= {
                    "encoder_mode": "frozen_embeddings",
                    "input_size": 518,
                    "preprocessing": "documented_native_dinov2_deterministic",
                    "cache_embeddings": True,
                    "embedding_batch_size_cpu": 8,
                    "embedding_batch_size_cuda": 16,
                    "pretrained_artifact": REFERENCE_ARTIFACTS[workload],
                }
            tasks.append(
                ExperimentTask(
                    task_id=f"inner.tuning.outer-{outer_fold}.{workload}",
                    stage="inner_tuning",
                    workload=workload,
                    outer_fold=outer_fold,
                    training_folds=development_folds,
                    validation_folds=development_folds,
                    evaluation_fold=None,
                    parameters=parameters,
                    expected_counts={"development_count": _fold_count(development_folds)},
                    required_artifact_roles=("oof_predictions",),
                )
            )
    return tuple(tasks)


def _safe_relative_artifact(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise DataIntegrityError(f"Artifact path must be safe and relative: {path_text!r}")
    if path.parts[0].startswith("."):
        raise DataIntegrityError(f"Artifact path may not use a hidden control name: {path_text!r}")
    return path


def _finite_nonnegative(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DataIntegrityError(f"Task payload {key!r} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise DataIntegrityError(f"Task payload {key!r} must be finite and non-negative")
    return numeric


def _require_count(payload: Mapping[str, Any], key: str, expected: int) -> None:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value != expected:
        raise DataIntegrityError(f"Task payload {key!r} must equal {expected}, found {value!r}")


def _alpha_key(value: float) -> str:
    return format(value, "g")


def _validate_task_payload(task: ExperimentTask, payload: Mapping[str, Any]) -> None:
    _canonical_json_bytes(dict(payload))
    for key, expected in task.expected_counts.items():
        _require_count(payload, key, expected)
    if task.stage == "inner_primary":
        epoch = payload.get("best_epoch")
        maximum = int(task.parameters["maximum_epochs"])
        if not isinstance(epoch, int) or isinstance(epoch, bool) or not 1 <= epoch <= maximum:
            raise DataIntegrityError(f"inner best_epoch must be in [1, {maximum}]")
        _finite_nonnegative(payload, "macro_category_mae")
    elif task.stage == "inner_tuning":
        fold_scores = payload.get("fold_scores")
        if not isinstance(fold_scores, dict):
            raise DataIntegrityError("inner tuning payload requires fold_scores")
        expected_alphas = {_alpha_key(float(value)) for value in task.parameters["alphas"]}
        if set(fold_scores) != expected_alphas:
            raise DataIntegrityError("inner tuning scores must cover the exact frozen alpha grid")
        expected_folds = {str(fold) for fold in task.validation_folds}
        for scores in fold_scores.values():
            if not isinstance(scores, dict) or set(scores) != expected_folds:
                raise DataIntegrityError("each alpha must score every frozen inner fold")
            for value in scores.values():
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise DataIntegrityError("inner tuning scores must be numeric")
                if not math.isfinite(float(value)) or float(value) < 0:
                    raise DataIntegrityError("inner tuning scores must be finite and non-negative")
    elif task.stage == "outer":
        _finite_nonnegative(payload, "macro_category_mae")
    if task.stage == "outer" and task.workload == "fixed_within_category_wrong_pair":
        count = payload.get("singleton_fallback_count")
        sample_ids = payload.get("singleton_fallback_sample_ids")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise DataIntegrityError("Wrong-pair payload requires a non-negative fallback count")
        if (
            not isinstance(sample_ids, list)
            or not all(isinstance(value, str) and value for value in sample_ids)
            or sample_ids != sorted(set(sample_ids))
            or len(sample_ids) != count
        ):
            raise DataIntegrityError("Wrong-pair fallback IDs must be unique, sorted, and counted")
    if task.stage == "outer" and task.workload in UNCERTAINTY_OUTER_WORKLOADS:
        policy = task.parameters.get("uncertainty_policy")
        if not isinstance(policy, dict):
            raise DataIntegrityError("Outer neural task lacks a frozen uncertainty policy")
        for key in ("interval_correction", "abstention_threshold"):
            value = payload.get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or float(value) != float(policy[key])
            ):
                raise DataIntegrityError(f"Outer payload {key!r} differs from frozen policy")
        retained_count = payload.get("retained_count")
        retained_ids = payload.get("retained_sample_ids")
        if (
            not isinstance(retained_count, int)
            or isinstance(retained_count, bool)
            or retained_count < 0
            or not isinstance(retained_ids, list)
            or not all(isinstance(value, str) and value for value in retained_ids)
            or retained_ids != sorted(set(retained_ids))
            or len(retained_ids) != retained_count
        ):
            raise DataIntegrityError("Outer retained IDs must be unique, sorted, and counted")


OOF_PREDICTION_FIELDS = (
    "alpha",
    "validation_fold",
    "sample_id",
    "target",
    "prediction",
)


def _read_csv_rows(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != fields:
                raise DataIntegrityError(
                    f"Artifact columns differ from the required schema: {path}"
                )
            rows: list[dict[str, str]] = []
            for raw in reader:
                if None in raw or any(value is None for value in raw.values()):
                    raise DataIntegrityError(f"Artifact contains a malformed CSV row: {path}")
                rows.append({key: str(value) for key, value in raw.items()})
    except (OSError, csv.Error) as exc:
        raise DataIntegrityError(f"Cannot read CSV artifact {path}: {exc}") from exc
    return rows


def _parse_finite(row: Mapping[str, str], field: str, artifact: Path) -> float:
    try:
        value = float(row[field])
    except (KeyError, ValueError) as exc:
        raise DataIntegrityError(f"Artifact has invalid {field!r}: {artifact}") from exc
    if not math.isfinite(value):
        raise DataIntegrityError(f"Artifact has non-finite {field!r}: {artifact}")
    return value


def _expected_prediction_records(
    task: ExperimentTask, records: Sequence[ManifestRecord]
) -> list[ManifestRecord]:
    if task.stage == "inner_primary":
        folds = set(task.validation_folds)
    elif task.stage == "outer" and task.evaluation_fold is not None:
        folds = {task.evaluation_fold}
    else:
        return []
    return sorted(
        (record for record in records if record.is_valid and record.outer_fold in folds),
        key=lambda record: record.sample_id,
    )


def _validate_prediction_artifact(
    task: ExperimentTask,
    payload: Mapping[str, Any],
    artifact: Path,
    manifest_records: Sequence[ManifestRecord],
) -> None:
    rows = _read_csv_rows(artifact, PREDICTION_FIELDS)
    expected = _expected_prediction_records(task, manifest_records)
    expected_by_id = {record.sample_id: record for record in expected}
    observed_ids = [row["sample_id"] for row in rows]
    expected_ids = [record.sample_id for record in expected]
    if observed_ids != expected_ids or len(set(observed_ids)) != len(observed_ids):
        raise DataIntegrityError(
            f"Prediction artifact must cover the requested rows exactly once in stable order: {artifact}"
        )

    expected_configuration = str(task.parameters.get("configuration", ""))
    expected_epoch = (
        int(payload["best_epoch"])
        if task.stage == "inner_primary"
        else int(task.parameters.get("epoch", 0))
    )
    targets: list[float] = []
    medians: list[float] = []
    categories: list[str] = []
    interval_widths: list[float] = []
    for row in rows:
        sample_id = row["sample_id"]
        source = expected_by_id[sample_id]
        try:
            row_fold = int(row["outer_fold"])
            row_epoch = int(row["epoch"])
        except ValueError as exc:
            raise DataIntegrityError(f"Prediction fold/epoch is invalid: {artifact}") from exc
        target = _parse_finite(row, "target", artifact)
        quantiles = tuple(_parse_finite(row, field, artifact) for field in ("q05", "q50", "q95"))
        if not 0.0 <= quantiles[0] <= quantiles[1] <= quantiles[2] <= 1.0:
            raise DataIntegrityError(f"Prediction quantiles are not ordered in [0,1]: {artifact}")
        if task.workload in POINT_OUTER_WORKLOADS and not (
            quantiles[0] == quantiles[1] == quantiles[2]
        ):
            raise DataIntegrityError(
                f"Point-baseline artifact contains non-point intervals: {artifact}"
            )
        if (
            row["category"] != source.category
            or row_fold != source.outer_fold
            or not math.isclose(target, source.leftover_fraction, rel_tol=0.0, abs_tol=1e-12)
            or row["workload"] != task.workload
            or row["configuration"] != expected_configuration
            or row_epoch != expected_epoch
        ):
            raise DataIntegrityError(
                f"Prediction metadata differs from the manifest/task for {sample_id}: {artifact}"
            )
        targets.append(target)
        medians.append(quantiles[1])
        categories.append(source.category)
        interval_widths.append(quantiles[2] - quantiles[0])

    reported_metric = payload.get("macro_category_mae")
    if reported_metric is not None:
        calculated = macro_category_mae(targets, medians, categories)
        if not math.isclose(calculated, float(reported_metric), rel_tol=1e-12, abs_tol=1e-12):
            raise DataIntegrityError(
                f"Prediction artifact metric differs from its payload: {artifact}"
            )
    if task.stage == "outer" and task.workload in UNCERTAINTY_OUTER_WORKLOADS:
        threshold = float(task.parameters["uncertainty_policy"]["abstention_threshold"])
        expected_retained = [
            sample_id
            for sample_id, width in zip(observed_ids, interval_widths, strict=True)
            if width <= threshold + 1e-12
        ]
        if payload["retained_sample_ids"] != expected_retained:
            raise DataIntegrityError(
                f"Retained IDs differ from the frozen abstention threshold: {artifact}"
            )


def _validate_oof_artifact(
    task: ExperimentTask,
    payload: Mapping[str, Any],
    artifact: Path,
    manifest_records: Sequence[ManifestRecord],
) -> None:
    rows = _read_csv_rows(artifact, OOF_PREDICTION_FIELDS)
    development = sorted(
        (
            record
            for record in manifest_records
            if record.is_valid and record.outer_fold in set(task.training_folds)
        ),
        key=lambda record: record.sample_id,
    )
    expected_by_id = {record.sample_id: record for record in development}
    alpha_keys = {_alpha_key(float(value)) for value in task.parameters["alphas"]}
    expected_keys = {(alpha, record.sample_id) for alpha in alpha_keys for record in development}
    observed_keys: set[tuple[str, str]] = set()
    observed_sequence: list[tuple[str, str]] = []
    fold_values: dict[tuple[str, int], tuple[list[float], list[float], list[str]]] = {}
    for row in rows:
        alpha = row["alpha"]
        sample_id = row["sample_id"]
        key = (alpha, sample_id)
        if key in observed_keys or key not in expected_keys:
            raise DataIntegrityError(f"OOF artifact has duplicate or unexpected rows: {artifact}")
        observed_keys.add(key)
        observed_sequence.append(key)
        source = expected_by_id[sample_id]
        try:
            validation_fold = int(row["validation_fold"])
        except ValueError as exc:
            raise DataIntegrityError(f"OOF validation fold is invalid: {artifact}") from exc
        target = _parse_finite(row, "target", artifact)
        prediction = _parse_finite(row, "prediction", artifact)
        if (
            validation_fold != source.outer_fold
            or validation_fold not in task.validation_folds
            or not math.isclose(target, source.leftover_fraction, rel_tol=0.0, abs_tol=1e-12)
            or not 0.0 <= prediction <= 1.0
        ):
            raise DataIntegrityError(
                f"OOF row differs from its declared validation sample: {sample_id}"
            )
        target_values, predictions, categories = fold_values.setdefault(
            (alpha, validation_fold), ([], [], [])
        )
        target_values.append(target)
        predictions.append(prediction)
        categories.append(source.category)
    if observed_keys != expected_keys:
        raise DataIntegrityError(
            f"OOF artifact must cover every alpha-by-development sample exactly once: {artifact}"
        )
    expected_sequence = [
        (_alpha_key(float(alpha)), record.sample_id)
        for alpha in task.parameters["alphas"]
        for fold in task.validation_folds
        for record in development
        if record.outer_fold == fold
    ]
    if observed_sequence != expected_sequence:
        raise DataIntegrityError(
            f"OOF artifact row order differs from the frozen order: {artifact}"
        )

    scores = payload["fold_scores"]
    assert isinstance(scores, dict)
    for (alpha, fold), (targets, predictions, categories) in fold_values.items():
        calculated = macro_category_mae(targets, predictions, categories)
        reported = float(scores[alpha][str(fold)])
        if not math.isclose(calculated, reported, rel_tol=1e-12, abs_tol=1e-12):
            raise DataIntegrityError(f"OOF artifact score differs from its payload: {artifact}")


def _expected_pairing_rows(records: Sequence[ManifestRecord], scope: str) -> list[dict[str, str]]:
    try:
        control = fixed_within_category_wrong_pairs(list(records))
    except ValueError as exc:
        raise DataIntegrityError(str(exc)) from exc
    return [
        {
            "sample_id": record.sample_id,
            "original_after_path": record.after_path,
            "wrong_after_path": control.after_path_by_sample[record.sample_id],
            "source_sample_id": control.source_sample_by_sample[record.sample_id],
            "rule": control.rule_by_sample[record.sample_id],
            "scope": scope,
        }
        for record in sorted(records, key=lambda value: value.sample_id)
    ]


def _validate_pairing_artifact(
    task: ExperimentTask,
    payload: Mapping[str, Any],
    artifact: Path,
    manifest_records: Sequence[ManifestRecord],
) -> None:
    rows = _read_csv_rows(artifact, PAIRING_MAP_FIELDS)
    training = [
        record
        for record in manifest_records
        if record.is_valid and record.outer_fold in set(task.training_folds)
    ]
    evaluation = _expected_prediction_records(task, manifest_records)
    expected = [
        *_expected_pairing_rows(training, "training"),
        *_expected_pairing_rows(evaluation, "evaluation"),
    ]
    if rows != expected:
        raise DataIntegrityError(
            "Wrong-pair map differs from the deterministic same-fold bijection"
        )
    if (
        len({row["sample_id"] for row in rows}) != len(rows)
        or {row["wrong_after_path"] for row in rows} != {row["original_after_path"] for row in rows}
        or any(row["sample_id"] == row["source_sample_id"] for row in rows)
    ):
        raise DataIntegrityError("Wrong-pair map must be complete, bijective, and self-pair free")
    fallback_ids = sorted(
        row["sample_id"] for row in rows if row["rule"].startswith("same_fold_singleton_swap")
    )
    if payload["singleton_fallback_sample_ids"] != fallback_ids or payload[
        "singleton_fallback_count"
    ] != len(fallback_ids):
        raise DataIntegrityError("Wrong-pair fallback payload differs from pairing map")


def _validate_semantic_artifacts(
    task: ExperimentTask,
    payload: Mapping[str, Any],
    artifact_paths: Mapping[str, Path],
    manifest_path: Path,
) -> None:
    """Bind every prediction row to the frozen manifest before accepting a task."""

    prediction_role = (
        "validation_predictions"
        if task.stage == "inner_primary"
        else "predictions"
        if task.stage == "outer"
        else None
    )
    if prediction_role is None and task.stage != "inner_tuning":
        return
    manifest_records = read_manifest(manifest_path)
    if prediction_role is not None:
        _validate_prediction_artifact(
            task, payload, artifact_paths[prediction_role], manifest_records
        )
        if task.workload == "fixed_within_category_wrong_pair":
            _validate_pairing_artifact(
                task, payload, artifact_paths["pairing_map"], manifest_records
            )
        return
    _validate_oof_artifact(task, payload, artifact_paths["oof_predictions"], manifest_records)


def verify_dataset_root(manifest_path: str | Path, dataset_root: str | Path) -> dict[str, Any]:
    """Re-hash every manifest image once before any workload may execute."""

    manifest = Path(manifest_path)
    root = Path(dataset_root)
    if not root.is_dir():
        raise DataIntegrityError(f"Dataset root is missing or not a directory: {root}")
    records = read_manifest(manifest)
    observed: dict[str, str] = {}
    for record in records:
        for relative_path, expected_hash in (
            (record.before_path, record.before_sha256),
            (record.after_path, record.after_sha256),
        ):
            candidate = root / relative_path
            if not candidate.is_file():
                raise DataIntegrityError(f"Manifest image is missing at run start: {relative_path}")
            actual_hash = observed.get(relative_path)
            if actual_hash is None:
                actual_hash = sha256_file(candidate)
                observed[relative_path] = actual_hash
            if actual_hash != expected_hash:
                raise DataIntegrityError(
                    f"Manifest image hash mismatch at run start: {relative_path}"
                )
    inventory = [{"path": path, "sha256": digest} for path, digest in sorted(observed.items())]
    return {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "manifest_sha256": sha256_file(manifest),
        "record_count": len(records),
        "unique_image_count": len(inventory),
        "image_inventory_sha256": _canonical_sha256(inventory),
    }


def _run_descriptor(
    protocol: FrozenProtocol, runner: TaskRunner, dataset_verification: Mapping[str, Any]
) -> dict[str, Any]:
    if not runner.fingerprint.strip():
        raise DataIntegrityError("Task runner fingerprint must be non-empty")
    core = {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "protocol": protocol.public_descriptor(),
        "runner_fingerprint": runner.fingerprint,
        "dataset_verification": dict(dataset_verification),
    }
    environment = getattr(runner, "environment", None)
    if environment is not None:
        if not isinstance(environment, dict):
            raise DataIntegrityError("Runner environment metadata must be an object")
        core["runner_environment"] = environment
    return core | {"run_id": _canonical_sha256(core)}


def _initialize_run(
    output_directory: Path,
    protocol: FrozenProtocol,
    runner: TaskRunner,
    dataset_verification: Mapping[str, Any],
) -> str:
    descriptor = _run_descriptor(protocol, runner, dataset_verification)
    run_file = output_directory / "run.json"
    if run_file.exists():
        existing = _read_json_object(run_file)
        if _canonical_json_bytes(existing) != _canonical_json_bytes(descriptor):
            raise DataIntegrityError(
                "Run identity differs from the existing output directory; use a new directory"
            )
    else:
        if output_directory.exists() and any(output_directory.iterdir()):
            raise DataIntegrityError(
                "Output directory is non-empty but has no immutable run.json identity"
            )
        output_directory.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(run_file, descriptor)
    return str(descriptor["run_id"])


def _task_directory(output_directory: Path, task: ExperimentTask) -> Path:
    return output_directory / "tasks" / task.task_id


def _artifact_inventory(workspace: Path, result: WorkloadResult) -> list[dict[str, Any]]:
    if set(result.artifacts) == set() or len(result.artifacts) != len(set(result.artifacts)):
        raise DataIntegrityError("Workload must declare unique artifact roles")
    inventory: list[dict[str, Any]] = []
    declared_paths: set[Path] = set()
    root = workspace.resolve()
    for role, path_text in sorted(result.artifacts.items()):
        if not role or role.startswith("_"):
            raise DataIntegrityError(f"Invalid artifact role {role!r}")
        relative = _safe_relative_artifact(path_text)
        artifact = workspace / relative
        if artifact.is_symlink() or not artifact.is_file():
            raise DataIntegrityError(f"Declared artifact is not a regular file: {relative}")
        try:
            artifact.resolve().relative_to(root)
        except ValueError as exc:
            raise DataIntegrityError(f"Artifact escaped its task workspace: {relative}") from exc
        if relative in declared_paths:
            raise DataIntegrityError(f"Artifact path declared twice: {relative}")
        declared_paths.add(relative)
        inventory.append(
            {
                "role": role,
                "path": (Path("workload") / relative).as_posix(),
                "size_bytes": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
            }
        )
    for candidate in workspace.rglob("*"):
        if candidate.is_symlink():
            raise DataIntegrityError(f"Symlinks are forbidden in task artifacts: {candidate}")
        if candidate.is_file() and candidate.relative_to(workspace) not in declared_paths:
            raise DataIntegrityError(
                f"Undeclared task artifact: {candidate.relative_to(workspace)}"
            )
    return inventory


def _validate_completed_task(
    task_directory: Path,
    *,
    task: ExperimentTask,
    protocol_id: str,
    runner_fingerprint: str,
    manifest_path: Path,
) -> dict[str, Any]:
    if not task_directory.is_dir():
        raise DataIntegrityError(f"Completed task directory is missing: {task_directory}")
    spec = _read_json_object(task_directory / "task.json")
    expected_spec = task.to_dict()
    if _canonical_json_bytes(spec) != _canonical_json_bytes(expected_spec):
        raise DataIntegrityError(f"Task specification changed on resume: {task.task_id}")
    result = _read_json_object(task_directory / "result.json")
    expected_identity = {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "status": "complete",
        "task_id": task.task_id,
        "protocol_id": protocol_id,
        "task_spec_sha256": _canonical_sha256(expected_spec),
        "runner_fingerprint": runner_fingerprint,
    }
    for key, expected in expected_identity.items():
        if result.get(key) != expected:
            raise DataIntegrityError(f"Completed task identity mismatch for {task.task_id}: {key}")
    payload = result.get("payload")
    artifacts = result.get("artifacts")
    if not isinstance(payload, dict) or not isinstance(artifacts, list):
        raise DataIntegrityError(f"Malformed task result: {task.task_id}")
    _validate_task_payload(task, payload)
    if result.get("payload_sha256") != _canonical_sha256(payload):
        raise DataIntegrityError(f"Task payload hash mismatch for {task.task_id}")
    roles: set[str] = set()
    declared_files: set[Path] = set()
    artifact_paths: dict[str, Path] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            raise DataIntegrityError(f"Malformed artifact inventory: {task.task_id}")
        role = item.get("role")
        path_text = item.get("path")
        if not isinstance(role, str) or not isinstance(path_text, str):
            raise DataIntegrityError(f"Malformed artifact identity: {task.task_id}")
        relative = _safe_relative_artifact(path_text)
        artifact = task_directory / relative
        if artifact.is_symlink() or not artifact.is_file():
            raise DataIntegrityError(f"Artifact missing on resume: {artifact}")
        if item.get("size_bytes") != artifact.stat().st_size or item.get("sha256") != sha256_file(
            artifact
        ):
            raise DataIntegrityError(f"Artifact hash/size mismatch on resume: {artifact}")
        if role in roles or relative in declared_files:
            raise DataIntegrityError(f"Duplicate artifact role/path for {task.task_id}")
        roles.add(role)
        declared_files.add(relative)
        artifact_paths[role] = artifact
    if len(artifacts) != len(task.required_artifact_roles) or roles != set(
        task.required_artifact_roles
    ):
        raise DataIntegrityError(f"Artifact roles differ for completed task {task.task_id}")
    actual_workload_files = {
        candidate.relative_to(task_directory)
        for candidate in (task_directory / "workload").rglob("*")
        if candidate.is_file()
    }
    if actual_workload_files != declared_files:
        raise DataIntegrityError(f"Undeclared or missing files in completed task {task.task_id}")
    _validate_semantic_artifacts(task, payload, artifact_paths, manifest_path)
    return result


def _execute_task(
    *,
    task: ExperimentTask,
    protocol: FrozenProtocol,
    runner: TaskRunner,
    output_directory: Path,
    dataset_root: Path,
) -> bool:
    task_directory = _task_directory(output_directory, task)
    if task_directory.exists():
        _validate_completed_task(
            task_directory,
            task=task,
            protocol_id=protocol.protocol_id,
            runner_fingerprint=runner.fingerprint,
            manifest_path=Path(protocol.input_paths["manifest"]),
        )
        return False
    task_directory.parent.mkdir(parents=True, exist_ok=True)
    attempts = output_directory / ".attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{task.task_id}.", dir=attempts) as temporary:
        staging = Path(temporary)
        workspace = staging / "workload"
        workspace.mkdir()
        request = TaskRequest(
            schema_version=ORCHESTRATION_SCHEMA_VERSION,
            protocol_id=protocol.protocol_id,
            manifest_path=protocol.input_paths["manifest"],
            dataset_root=str(dataset_root.resolve()),
            task=task,
        )
        result = runner.execute(request, workspace)
        if not isinstance(result, WorkloadResult):
            raise DataIntegrityError("Task runner must return WorkloadResult")
        _validate_task_payload(task, result.payload)
        if set(result.artifacts) != set(task.required_artifact_roles):
            raise DataIntegrityError(
                f"Task {task.task_id} must produce roles {task.required_artifact_roles!r}"
            )
        artifact_paths = {
            role: workspace / _safe_relative_artifact(path)
            for role, path in result.artifacts.items()
        }
        _validate_semantic_artifacts(
            task,
            result.payload,
            artifact_paths,
            Path(protocol.input_paths["manifest"]),
        )
        inventory = _artifact_inventory(workspace, result)
        spec = task.to_dict()
        metadata = {
            "schema_version": ORCHESTRATION_SCHEMA_VERSION,
            "status": "complete",
            "task_id": task.task_id,
            "protocol_id": protocol.protocol_id,
            "task_spec_sha256": _canonical_sha256(spec),
            "runner_fingerprint": runner.fingerprint,
            "payload": result.payload,
            "payload_sha256": _canonical_sha256(result.payload),
            "artifacts": inventory,
        }
        _atomic_write_json(staging / "task.json", spec)
        _atomic_write_json(staging / "result.json", metadata)
        if task_directory.exists():
            raise DataIntegrityError(f"Task completed concurrently: {task.task_id}")
        staging.replace(task_directory)
    return True


def _task_result(
    output_directory: Path,
    protocol: FrozenProtocol,
    runner: TaskRunner,
    task: ExperimentTask,
) -> dict[str, Any]:
    return _validate_completed_task(
        _task_directory(output_directory, task),
        task=task,
        protocol_id=protocol.protocol_id,
        runner_fingerprint=runner.fingerprint,
        manifest_path=Path(protocol.input_paths["manifest"]),
    )


def _select_alpha(task: ExperimentTask, payload: Mapping[str, Any]) -> tuple[float, float]:
    fold_scores = payload["fold_scores"]
    assert isinstance(fold_scores, dict)  # validated by _validate_task_payload
    means: dict[float, float] = {}
    for alpha in (float(value) for value in task.parameters["alphas"]):
        scores = fold_scores[_alpha_key(alpha)]
        assert isinstance(scores, dict)
        means[alpha] = sum(float(value) for value in scores.values()) / len(scores)
    selected = min(means, key=lambda alpha: (means[alpha], alpha))
    return selected, means[selected]


def _selection_path(output_directory: Path, outer_fold: int) -> Path:
    return output_directory / "selections" / f"outer-{outer_fold}.json"


def _artifact_path_for_role(
    output_directory: Path,
    task: ExperimentTask,
    result: Mapping[str, Any],
    role: str,
) -> tuple[Path, str]:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        raise DataIntegrityError(f"Task {task.task_id} has no artifact inventory")
    matches = [item for item in artifacts if isinstance(item, dict) and item.get("role") == role]
    if len(matches) != 1 or not isinstance(matches[0].get("path"), str):
        raise DataIntegrityError(f"Task {task.task_id} has no unique {role!r} artifact")
    path = _task_directory(output_directory, task) / _safe_relative_artifact(matches[0]["path"])
    digest = matches[0].get("sha256")
    if not isinstance(digest, str) or digest != sha256_file(path):
        raise DataIntegrityError(f"Task {task.task_id} {role!r} artifact hash is stale")
    return path, digest


def _uncertainty_policy_from_inner(
    output_directory: Path,
    protocol: FrozenProtocol,
    selected_tasks: Sequence[tuple[ExperimentTask, Mapping[str, Any]]],
) -> dict[str, Any]:
    targets: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    sources: list[dict[str, Any]] = []
    for task, result in selected_tasks:
        path, artifact_hash = _artifact_path_for_role(
            output_directory, task, result, "validation_predictions"
        )
        rows = _read_csv_rows(path, PREDICTION_FIELDS)
        targets.extend(float(row["target"]) for row in rows)
        lower.extend(float(row["q05"]) for row in rows)
        upper.extend(float(row["q95"]) for row in rows)
        sources.append(
            {
                "task_id": task.task_id,
                "validation_fold": task.validation_folds[0],
                "result_sha256": sha256_file(
                    _task_directory(output_directory, task) / "result.json"
                ),
                "validation_predictions_sha256": artifact_hash,
            }
        )
    nominal = float(protocol.config["uncertainty"]["nominal_coverage"])
    maximum_width = float(protocol.config["uncertainty"]["maximum_abstention_width"])
    retention_quantile = float(protocol.config["uncertainty"]["retention_quantile"])
    target_array = np.asarray(targets, dtype=np.float64)
    low_array = np.asarray(lower, dtype=np.float64)
    high_array = np.asarray(upper, dtype=np.float64)
    correction = interval_correction(target_array, low_array, high_array, coverage=nominal)
    corrected_low, corrected_high = correct_intervals(low_array, high_array, correction)
    widths = corrected_high - corrected_low
    width_quantile = float(np.quantile(widths, retention_quantile, method="higher"))
    threshold = derive_abstention_threshold(
        corrected_low,
        corrected_high,
        maximum_width=maximum_width,
        retention_quantile=retention_quantile,
    )
    return {
        "method": "selected_primary_inner_validation_predictions_only",
        "nominal_coverage": nominal,
        "interval_correction": correction,
        "retention_quantile": retention_quantile,
        "retained_width_quantile": width_quantile,
        "maximum_abstention_width": maximum_width,
        "abstention_threshold": threshold,
        "calibration_count": len(targets),
        "sources": sorted(sources, key=lambda item: item["task_id"]),
    }


def _expected_outer_selection(
    output_directory: Path,
    protocol: FrozenProtocol,
    runner: TaskRunner,
    outer_fold: int,
) -> dict[str, Any]:
    tasks = build_inner_tasks(protocol)
    task_by_id = {task.task_id: task for task in tasks}
    source_entries: list[dict[str, str]] = []
    inner_runs: list[InnerRun] = []
    primary_results: dict[tuple[int, str], tuple[ExperimentTask, Mapping[str, Any]]] = {}
    for validation_fold in inner_folds(outer_fold):
        for configuration in ("M1", "M2"):
            task_id = (
                f"inner.primary.outer-{outer_fold}.validation-{validation_fold}."
                f"{configuration.lower()}"
            )
            task = task_by_id[task_id]
            result = _task_result(output_directory, protocol, runner, task)
            payload = result["payload"]
            inner_runs.append(
                InnerRun(
                    configuration=configuration,
                    fold=validation_fold,
                    best_epoch=int(payload["best_epoch"]),
                    macro_category_mae=float(payload["macro_category_mae"]),
                )
            )
            primary_results[(validation_fold, configuration)] = (task, result)
            result_path = _task_directory(output_directory, task) / "result.json"
            source_entries.append({"task_id": task_id, "sha256": sha256_file(result_path)})
    primary = select_inner_configuration(inner_runs)
    if not 1 <= primary.epoch <= protocol.maximum_epochs:
        raise DataIntegrityError("Selected primary epoch is outside the frozen range")
    tuned: dict[str, dict[str, float]] = {}
    for workload in TUNED_WORKLOADS:
        task_id = f"inner.tuning.outer-{outer_fold}.{workload}"
        task = task_by_id[task_id]
        result = _task_result(output_directory, protocol, runner, task)
        selected_alpha, score = _select_alpha(task, result["payload"])
        if selected_alpha not in protocol.ridge_alphas:
            raise DataIntegrityError("Selected alpha is outside the frozen grid")
        tuned[workload] = {
            "alpha": selected_alpha,
            "mean_inner_macro_category_mae": score,
        }
        source_entries.append(
            {
                "task_id": task_id,
                "sha256": sha256_file(_task_directory(output_directory, task) / "result.json"),
            }
        )
    selected_tasks = [
        primary_results[(fold, primary.configuration)] for fold in inner_folds(outer_fold)
    ]
    return {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "kind": "outer_selection",
        "information_boundary": "inner_development_predictions_only",
        "protocol_id": protocol.protocol_id,
        "outer_fold": outer_fold,
        "primary": {
            "configuration": primary.configuration,
            "epoch": primary.epoch,
            "mean_inner_macro_category_mae": primary.mean_macro_category_mae,
        },
        "tuned_alphas": tuned,
        "uncertainty_policy": _uncertainty_policy_from_inner(
            output_directory, protocol, selected_tasks
        ),
        "sources": sorted(source_entries, key=lambda item: item["task_id"]),
    }


def _expected_final_choice(
    output_directory: Path, protocol: FrozenProtocol, runner: TaskRunner
) -> dict[str, Any]:
    outer_folds = sorted(FROZEN_CATEGORY_FOLDS)
    outer_payloads = [
        _read_selection(output_directory, protocol, runner, fold) for fold in outer_folds
    ]
    selections = [
        SelectedConfiguration(
            configuration=str(payload["primary"]["configuration"]),
            epoch=int(payload["primary"]["epoch"]),
            mean_macro_category_mae=float(payload["primary"]["mean_inner_macro_category_mae"]),
        )
        for payload in outer_payloads
    ]
    counts = {
        name: sum(selection.configuration == name for selection in selections)
        for name in MODEL_CONFIGURATIONS
    }
    chosen = min(("M1", "M2"), key=lambda name: (-counts[name], 0 if name == "M1" else 1))
    policy_records: list[dict[str, Any]] = []
    for fold, payload, selection in zip(outer_folds, outer_payloads, selections, strict=True):
        policy = payload.get("uncertainty_policy")
        if not isinstance(policy, dict):
            raise DataIntegrityError(f"Outer selection {fold} has no valid uncertainty policy")
        correction = policy.get("interval_correction")
        threshold = policy.get("abstention_threshold")
        if (
            not isinstance(correction, (int, float))
            or isinstance(correction, bool)
            or not math.isfinite(float(correction))
            or not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not math.isfinite(float(threshold))
        ):
            raise DataIntegrityError(
                f"Outer selection {fold} has non-finite uncertainty policy values"
            )
        policy_records.append(
            {
                "outer_fold": fold,
                "selected_primary_configuration": selection.configuration,
                "interval_correction": float(correction),
                "abstention_threshold": float(threshold),
            }
        )
    included_policies = [
        record for record in policy_records if record["selected_primary_configuration"] == chosen
    ]
    excluded_policies = [
        {
            "outer_fold": record["outer_fold"],
            "selected_primary_configuration": record["selected_primary_configuration"],
        }
        for record in policy_records
        if record["selected_primary_configuration"] != chosen
    ]
    if len(included_policies) < 3:
        raise DataIntegrityError(
            "Final modal configuration has fewer than three matching outer-selection policies"
        )
    return {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "kind": "final_deploy_choice",
        "information_boundary": "inner_selections_only_no_outer_metrics",
        "protocol_id": protocol.protocol_id,
        "configuration": chosen,
        "epoch": int(median(selection.epoch for selection in selections)),
        "uncertainty_policy": {
            "method": ("median_of_inner_only_outer_policies_matching_final_configuration"),
            "selection_rule": (
                "include_only_outer_selections_whose_selected_primary_configuration_"
                "matches_the_final_modal_configuration"
            ),
            "final_configuration": chosen,
            "minimum_matching_outer_selections": 3,
            "included_outer_selections": included_policies,
            "excluded_outer_selections": excluded_policies,
            "interval_correction": float(
                median(float(policy["interval_correction"]) for policy in included_policies)
            ),
            "abstention_threshold": float(
                median(float(policy["abstention_threshold"]) for policy in included_policies)
            ),
        },
        "outer_selection_sources": [
            {
                "outer_fold": fold,
                "sha256": sha256_file(_selection_path(output_directory, fold)),
            }
            for fold in sorted(FROZEN_CATEGORY_FOLDS)
        ],
    }


def _write_selections(output_directory: Path, protocol: FrozenProtocol, runner: TaskRunner) -> int:
    written = 0
    for outer_fold in sorted(FROZEN_CATEGORY_FOLDS):
        selection = _expected_outer_selection(output_directory, protocol, runner, outer_fold)
        if _write_or_validate_json(_selection_path(output_directory, outer_fold), selection):
            written += 1
    final_choice = _expected_final_choice(output_directory, protocol, runner)
    if _write_or_validate_json(output_directory / "selections" / "final.json", final_choice):
        written += 1
    return written


def _read_selection(
    output_directory: Path,
    protocol: FrozenProtocol,
    runner: TaskRunner,
    outer_fold: int,
) -> dict[str, Any]:
    path = _selection_path(output_directory, outer_fold)
    selection = _read_json_object(path)
    expected = _expected_outer_selection(output_directory, protocol, runner, outer_fold)
    if _canonical_json_bytes(selection) != _canonical_json_bytes(expected):
        raise DataIntegrityError(f"Invalid, tampered, or stale outer selection: {path}")
    return selection


def build_outer_tasks(
    protocol: FrozenProtocol, output_directory: Path, runner: TaskRunner
) -> tuple[ExperimentTask, ...]:
    """Build once-opened outer tasks from immutable inner-only selections."""

    tasks: list[ExperimentTask] = []
    for outer_fold in sorted(FROZEN_CATEGORY_FOLDS):
        selection = _read_selection(output_directory, protocol, runner, outer_fold)
        development = inner_folds(outer_fold)
        primary = selection.get("primary")
        tuned = selection.get("tuned_alphas")
        uncertainty_policy = selection.get("uncertainty_policy")
        if (
            not isinstance(primary, dict)
            or not isinstance(tuned, dict)
            or not isinstance(uncertainty_policy, dict)
        ):
            raise DataIntegrityError(f"Malformed selection for outer fold {outer_fold}")
        selected_configuration = str(primary.get("configuration"))
        selected_epoch = primary.get("epoch")
        if selected_configuration not in MODEL_CONFIGURATIONS or not isinstance(
            selected_epoch, int
        ):
            raise DataIntegrityError(f"Malformed primary selection for outer fold {outer_fold}")
        for workload in OUTER_WORKLOADS:
            parameters: dict[str, Any] = {
                "seed": protocol.confirmatory_seed,
                "outer_open_policy": "open_once_after_inner_selection",
            }
            if workload in {
                PRIMARY_WORKLOAD,
                "after_only_mobilenet",
                "fixed_within_category_wrong_pair",
            }:
                parameters |= _model_parameters(protocol, selected_configuration)
                parameters["epoch"] = selected_epoch
            if workload == PRIMARY_WORKLOAD:
                parameters["uncertainty_policy"] = uncertainty_policy
            if workload == "fixed_within_category_wrong_pair":
                parameters["pairing_rule"] = (
                    "within_category_except_deterministic_same_fold_singleton_swap_fallback"
                )
                parameters["singleton_fallback"] = (
                    "swap_with_stable_preimage_of_same_fold_non_singleton_donor_after"
                )
            if workload == "paired_resnet50":
                parameters |= _model_parameters(protocol, "M1")
                parameters |= {
                    "epoch": selected_epoch,
                    "fixed_recipe": "M1_with_primary_selected_epoch",
                    "pretrained_artifact": REFERENCE_ARTIFACTS[workload],
                }
            if workload in TUNED_WORKLOADS:
                tuned_value = tuned.get(workload)
                if not isinstance(tuned_value, dict) or not isinstance(
                    tuned_value.get("alpha"), (int, float)
                ):
                    raise DataIntegrityError(
                        f"Missing frozen alpha for {workload}, fold {outer_fold}"
                    )
                parameters["alpha"] = float(tuned_value["alpha"])
            if workload == "frozen_paired_dinov2":
                parameters |= {
                    "encoder_mode": "frozen_embeddings",
                    "input_size": 518,
                    "preprocessing": "documented_native_dinov2_deterministic",
                    "cache_embeddings": True,
                    "embedding_batch_size_cpu": 8,
                    "embedding_batch_size_cuda": 16,
                    "pretrained_artifact": REFERENCE_ARTIFACTS[workload],
                }
            if workload == "training_median":
                parameters["fit_scope"] = "development_targets_only"
            if workload == "observer_score_context_only":
                parameters["context_only"] = True
            tasks.append(
                ExperimentTask(
                    task_id=f"outer.fold-{outer_fold}.{workload}",
                    stage="outer",
                    workload=workload,
                    outer_fold=outer_fold,
                    training_folds=development,
                    validation_folds=(),
                    evaluation_fold=outer_fold,
                    parameters=parameters,
                    expected_counts={
                        "training_count": _fold_count(development),
                        "prediction_count": EXPECTED_FOLD_COUNTS[outer_fold],
                    },
                    required_artifact_roles=(
                        ("predictions", "pairing_map")
                        if workload == "fixed_within_category_wrong_pair"
                        else ("predictions",)
                    ),
                )
            )
    return tuple(tasks)


def build_final_task(
    protocol: FrozenProtocol, output_directory: Path, runner: TaskRunner
) -> ExperimentTask:
    final_path = output_directory / "selections" / "final.json"
    final = _read_json_object(final_path)
    expected_final = _expected_final_choice(output_directory, protocol, runner)
    if _canonical_json_bytes(final) != _canonical_json_bytes(expected_final):
        raise DataIntegrityError("Final deployment choice is stale or test-informed")
    configuration = str(final.get("configuration"))
    epoch = final.get("epoch")
    if configuration not in MODEL_CONFIGURATIONS or not isinstance(epoch, int):
        raise DataIntegrityError("Final deployment choice is malformed")
    parameters = _model_parameters(protocol, configuration) | {
        "epoch": epoch,
        "training_scope": "all_514_valid_pairs",
        "selection_source": "inner_only_modal_configuration_and_median_epoch",
        "uncertainty_policy": final["uncertainty_policy"],
    }
    return ExperimentTask(
        task_id="final.deploy.paired_mobilenet",
        stage="final",
        workload=PRIMARY_WORKLOAD,
        outer_fold=None,
        training_folds=tuple(sorted(FROZEN_CATEGORY_FOLDS)),
        validation_folds=(),
        evaluation_fold=None,
        parameters=parameters,
        expected_counts={"training_count": sum(EXPECTED_FOLD_COUNTS.values())},
        required_artifact_roles=("model_checkpoint",),
    )


def _require_outer_complete(
    protocol: FrozenProtocol, runner: TaskRunner, output_directory: Path
) -> None:
    for task in build_outer_tasks(protocol, output_directory, runner):
        _task_result(output_directory, protocol, runner, task)


def execute_experiment(
    *,
    audit_report_path: str | Path,
    manifest_path: str | Path,
    dataset_root: str | Path,
    output_directory: str | Path,
    runner: TaskRunner,
    stage: str,
    config_path: str | Path = DEFAULT_EXPERIMENT_CONFIG,
    folds_path: str | Path = DEFAULT_FOLDS_CONFIG,
) -> ExperimentRunSummary:
    """Execute one explicitly requested stage with immutable resume semantics."""

    allowed = {"inner", "select", "outer", "final", "all"}
    if stage not in allowed:
        raise ValueError(f"stage must be one of {sorted(allowed)!r}")
    preflight, protocol = protocol_preflight(
        audit_report_path=audit_report_path,
        manifest_path=manifest_path,
        config_path=config_path,
        folds_path=folds_path,
    )
    if preflight.status != "ready" or protocol is None:
        raise DataIntegrityError(f"Experiment protocol is blocked: {preflight.blocker}")
    output = Path(output_directory)
    dataset_verification = verify_dataset_root(protocol.input_paths["manifest"], dataset_root)
    run_id = _initialize_run(output, protocol, runner, dataset_verification)
    executed = resumed = selections_written = planned = 0

    if stage in {"inner", "all"}:
        inner_tasks = build_inner_tasks(protocol)
        planned += len(inner_tasks)
        for task in inner_tasks:
            if _execute_task(
                task=task,
                protocol=protocol,
                runner=runner,
                output_directory=output,
                dataset_root=Path(dataset_root),
            ):
                executed += 1
            else:
                resumed += 1
    if stage in {"select", "all"}:
        planned += 6
        selections_written += _write_selections(output, protocol, runner)
    if stage in {"outer", "all"}:
        outer_tasks = build_outer_tasks(protocol, output, runner)
        planned += len(outer_tasks)
        for task in outer_tasks:
            if _execute_task(
                task=task,
                protocol=protocol,
                runner=runner,
                output_directory=output,
                dataset_root=Path(dataset_root),
            ):
                executed += 1
            else:
                resumed += 1
    if stage in {"final", "all"}:
        _require_outer_complete(protocol, runner, output)
        final_task = build_final_task(protocol, output, runner)
        planned += 1
        if _execute_task(
            task=final_task,
            protocol=protocol,
            runner=runner,
            output_directory=output,
            dataset_root=Path(dataset_root),
        ):
            executed += 1
        else:
            resumed += 1
    return ExperimentRunSummary(
        status="complete",
        stage=stage,
        protocol_id=protocol.protocol_id,
        run_id=run_id,
        planned_tasks=planned,
        executed_tasks=executed,
        resumed_tasks=resumed,
        selections_written=selections_written,
        output_directory=output.as_posix(),
    )


class CommandTaskRunner:
    """Invoke a pinned external worker through a small JSON file contract."""

    def __init__(self, command: Sequence[str]) -> None:
        if not command or not all(part for part in command):
            raise ValueError("Worker command must contain at least one non-empty argument")
        self.command = tuple(command)
        command_files: list[dict[str, str]] = []
        for part in self.command:
            candidate = Path(part)
            if candidate.is_file():
                command_files.append(
                    {"path": str(candidate.resolve()), "sha256": sha256_file(candidate)}
                )
        self._fingerprint = _canonical_sha256(
            {"command": list(self.command), "command_files": command_files}
        )

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def execute(self, request: TaskRequest, workspace: Path) -> WorkloadResult:
        control_directory = workspace.parent
        request_path = control_directory / "worker-request.json"
        response_path = control_directory / "worker-response.json"
        _atomic_write_json(request_path, request.to_dict())
        completed = subprocess.run(
            [*self.command, str(request_path), str(workspace), str(response_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise DataIntegrityError(
                "Worker failed for "
                f"{request.task.task_id} with exit {completed.returncode}: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        response = _read_json_object(response_path)
        if response.get("schema_version") != ORCHESTRATION_SCHEMA_VERSION:
            raise DataIntegrityError("Worker response schema_version mismatch")
        if response.get("task_id") != request.task.task_id:
            raise DataIntegrityError("Worker response task_id mismatch")
        payload = response.get("payload")
        artifacts = response.get("artifacts")
        if not isinstance(payload, dict) or not isinstance(artifacts, dict):
            raise DataIntegrityError("Worker response requires object payload and artifacts")
        if not all(
            isinstance(key, str) and isinstance(value, str) for key, value in artifacts.items()
        ):
            raise DataIntegrityError("Worker artifact mapping must contain string keys and paths")
        return WorkloadResult(payload=payload, artifacts=dict(artifacts))


def parse_worker_command(worker: str | Path, arguments: Sequence[str]) -> tuple[str, ...]:
    """Build a non-shell worker command while rejecting ambiguous empty input."""

    worker_text = str(worker).strip()
    if not worker_text:
        raise ValueError("Worker path must be non-empty")
    return (worker_text, *(str(argument) for argument in arguments))


def describe_worker_command(command: Sequence[str]) -> str:
    """Return a display-only command string; execution never uses a shell."""

    return shlex.join(command)
