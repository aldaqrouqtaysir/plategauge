"""Isolated execution for the frozen secondary same-category diagnostic.

The confirmatory orchestrator is intentionally not extended here: its source
files are part of the accepted production-runner fingerprint.  This module
reuses the exact inner-only fold recipes, but owns a separate immutable run,
task, prediction, and report contract.  Fitting never reads an outer result;
only the explicit aggregate stage opens validated confirmatory predictions.
"""

from __future__ import annotations

import csv
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import numpy as np

from .data import (
    DEFAULT_AUDIT_REPORT,
    DEFAULT_DATASET_ROOT,
    DEFAULT_MANIFEST,
    sha256_file,
)
from .errors import DataIntegrityError
from .metrics import (
    category_bootstrap_mae_difference,
    macro_category_mae,
    regression_metrics,
)
from .orchestration import (
    DEFAULT_EXPERIMENT_CONFIG,
    DEFAULT_FOLDS_CONFIG,
    DEFAULT_RUN_DIRECTORY,
    PRIMARY_WORKLOAD,
    ExperimentTask,
    FrozenProtocol,
    TaskRequest,
    WorkloadResult,
    _artifact_inventory,
    _atomic_write_json,
    _canonical_json_bytes,
    _canonical_sha256,
    _read_json_object,
    _safe_relative_artifact,
    _write_or_validate_json,
    build_outer_tasks,
    protocol_preflight,
    verify_dataset_root,
)
from .same_category_split import validate_split_artifact
from .schema import ManifestRecord, read_manifest

# ProductionTaskRunner is defined in workloads, but importing its implementation
# at module import time would make the light, read-only helpers require Torch.
from .workloads import ProductionTaskRunner

SCHEMA_VERSION = "1.0"
DIAGNOSTIC_KIND = "secondary_same_category_diagnostic"
FOLD_COUNT = 5
EXPECTED_VALID_ROWS = 514
EXPECTED_SEEN_ROWS = 511
EXPECTED_SEEN_CATEGORIES = 31
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260919

DEFAULT_SPLIT_CONFIG = Path("configs/same_category_folds_v1.json")
DEFAULT_SPLIT_REPORT = Path("reports/data_gate/same_category_folds_v1_validation.json")
DEFAULT_DIAGNOSTIC_DIRECTORY = Path("reports/experiments/same_category_v1")
IMPLEMENTATION_SOURCE_PATH = Path("src/plategauge/same_category_diagnostic.py")

FROZEN_SPLIT_SHA256 = "961fc17d826bf16637d31208c0743139a5ef47548e7bc6e9a56641a4f2ae387d"
FROZEN_SPLIT_ID = "129580d2a5560e8ad1f82ffca99bbb10e18d876a375603bbe0c3fb4b038ea1a2"
FROZEN_SPLIT_REPORT_SHA256 = "2f07288729ca49a7e16da30e105175922ec39a9415fde71845a5143097916f06"

DIAGNOSTIC_PREDICTION_FIELDS = (
    "sample_id",
    "category",
    "diagnostic_fold",
    "target",
    "raw_q05",
    "raw_q50",
    "raw_q95",
    "configuration",
    "epoch",
    "category_seen_in_training",
)


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"Non-finite JSON constant is forbidden: {value}")


def _strict_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DataIntegrityError(f"Cannot read strict JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataIntegrityError(f"JSON root must be an object: {path}")
    return cast(dict[str, Any], payload)


@dataclass(frozen=True, slots=True)
class DiagnosticPrediction:
    """One raw-quantile prediction under the diagnostic row assignment."""

    sample_id: str
    category: str
    diagnostic_fold: int
    target: float
    raw_q05: float
    raw_q50: float
    raw_q95: float
    configuration: str
    epoch: int
    category_seen_in_training: bool

    def __post_init__(self) -> None:
        values = (self.target, self.raw_q05, self.raw_q50, self.raw_q95)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Diagnostic prediction values must be finite")
        if not 0.0 <= self.target <= 1.0:
            raise ValueError("Diagnostic target must lie in [0,1]")
        if not 0.0 <= self.raw_q05 <= self.raw_q50 <= self.raw_q95 <= 1.0:
            raise ValueError("Raw diagnostic quantiles must be ordered in [0,1]")
        if self.diagnostic_fold not in range(FOLD_COUNT):
            raise ValueError("Diagnostic fold must be in [0,4]")
        if self.configuration not in {"M1", "M2"} or self.epoch < 1:
            raise ValueError("Diagnostic recipe configuration/epoch is invalid")

    def to_row(self) -> dict[str, str]:
        return {
            "sample_id": self.sample_id,
            "category": self.category,
            "diagnostic_fold": str(self.diagnostic_fold),
            "target": format(self.target, ".17g"),
            "raw_q05": format(self.raw_q05, ".17g"),
            "raw_q50": format(self.raw_q50, ".17g"),
            "raw_q95": format(self.raw_q95, ".17g"),
            "configuration": self.configuration,
            "epoch": str(self.epoch),
            "category_seen_in_training": ("true" if self.category_seen_in_training else "false"),
        }


@dataclass(frozen=True, slots=True)
class DiagnosticContext:
    protocol: FrozenProtocol
    confirmatory_run: dict[str, Any]
    records: tuple[ManifestRecord, ...]
    assignments: dict[str, int]
    source_tasks: tuple[ExperimentTask, ...]
    dataset_verification: dict[str, Any]
    split_path: Path
    split_report_path: Path
    confirmatory_directory: Path


class _RecordedRunner:
    """Reconstruct inner-only selections without executing a workload."""

    def __init__(self, fingerprint: str) -> None:
        if not fingerprint:
            raise DataIntegrityError("Confirmatory runner fingerprint is empty")
        self._fingerprint = fingerprint

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def execute(self, request: TaskRequest, workspace: Path) -> WorkloadResult:
        del request, workspace
        raise DataIntegrityError("Recorded runner is read-only")


def _validate_confirmatory_run(
    path: Path, protocol: FrozenProtocol, manifest_path: Path
) -> dict[str, Any]:
    run = _strict_json_object(path)
    run_id = run.get("run_id")
    core = {key: value for key, value in run.items() if key != "run_id"}
    if not isinstance(run_id, str) or run_id != _canonical_sha256(core):
        raise DataIntegrityError("Confirmatory run_id does not match its descriptor")
    protocol_payload = run.get("protocol")
    if (
        run.get("schema_version") != SCHEMA_VERSION
        or not isinstance(protocol_payload, dict)
        or protocol_payload.get("protocol_id") != protocol.protocol_id
    ):
        raise DataIntegrityError("Confirmatory run differs from the frozen protocol")
    input_hashes = protocol_payload.get("input_hashes")
    if not isinstance(input_hashes, dict) or input_hashes.get("manifest") != sha256_file(
        manifest_path
    ):
        raise DataIntegrityError("Confirmatory run is not bound to the supplied manifest")
    fingerprint = run.get("runner_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise DataIntegrityError("Confirmatory runner fingerprint is malformed")
    return run


def _load_frozen_assignments(
    split_path: Path,
    split_report_path: Path,
    manifest_path: Path,
    confirmatory_run_path: Path,
) -> tuple[dict[str, int], dict[str, Any]]:
    if sha256_file(split_path) != FROZEN_SPLIT_SHA256:
        raise DataIntegrityError("Same-category split bytes differ from the frozen hash")
    if sha256_file(split_report_path) != FROZEN_SPLIT_REPORT_SHA256:
        raise DataIntegrityError("Same-category freeze report differs from the frozen hash")
    split = _strict_json_object(split_path)
    report = _strict_json_object(split_report_path)
    try:
        validation = validate_split_artifact(split, manifest_path, confirmatory_run_path)
    except ValueError as exc:
        raise DataIntegrityError(f"Cannot reproduce same-category split: {exc}") from exc
    if (
        split.get("split_id") != FROZEN_SPLIT_ID
        or not validation.get("passed")
        or not report.get("passed")
        or report.get("split_id") != FROZEN_SPLIT_ID
        or report.get("config_sha256") != FROZEN_SPLIT_SHA256
        or report.get("frozen_before_outer_results") is not True
        or report.get("outer_result_artifact_count_at_freeze") != 0
        or report.get("outer_result_paths_at_freeze") != []
    ):
        raise DataIntegrityError("Same-category split/freeze evidence is invalid")
    raw_assignments = split.get("assignments")
    if not isinstance(raw_assignments, list):
        raise DataIntegrityError("Same-category split has no assignment list")
    assignments: dict[str, int] = {}
    for raw in raw_assignments:
        if not isinstance(raw, dict):
            raise DataIntegrityError("Same-category assignment row is malformed")
        sample_id = raw.get("sample_id")
        fold = raw.get("diagnostic_fold")
        if (
            not isinstance(sample_id, str)
            or not isinstance(fold, int)
            or isinstance(fold, bool)
            or fold not in range(FOLD_COUNT)
            or sample_id in assignments
        ):
            raise DataIntegrityError("Same-category assignment identity is invalid")
        assignments[sample_id] = fold
    return assignments, split


def _require_matching_runner(run: dict[str, Any], runner: ProductionTaskRunner) -> None:
    if runner.fingerprint != run.get("runner_fingerprint"):
        raise DataIntegrityError(
            "Diagnostic execution requires the exact confirmatory production-runner fingerprint"
        )


def _eligible_ids(
    records: tuple[ManifestRecord, ...], assignments: dict[str, int]
) -> tuple[str, ...]:
    eligible: list[str] = []
    for record in records:
        fold = assignments[record.sample_id]
        if any(
            other.category == record.category and assignments[other.sample_id] != fold
            for other in records
        ):
            eligible.append(record.sample_id)
    return tuple(sorted(eligible))


def load_diagnostic_context(
    *,
    runner: ProductionTaskRunner,
    audit_report_path: str | Path = DEFAULT_AUDIT_REPORT,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    dataset_root: str | Path = DEFAULT_DATASET_ROOT,
    config_path: str | Path = DEFAULT_EXPERIMENT_CONFIG,
    folds_path: str | Path = DEFAULT_FOLDS_CONFIG,
    confirmatory_directory: str | Path = DEFAULT_RUN_DIRECTORY,
    split_path: str | Path = DEFAULT_SPLIT_CONFIG,
    split_report_path: str | Path = DEFAULT_SPLIT_REPORT,
) -> DiagnosticContext:
    """Validate all frozen inputs without reading any outer result artifact."""

    manifest = Path(manifest_path)
    confirmatory = Path(confirmatory_directory)
    split = Path(split_path)
    split_report = Path(split_report_path)
    preflight, protocol = protocol_preflight(
        audit_report_path=audit_report_path,
        manifest_path=manifest,
        config_path=config_path,
        folds_path=folds_path,
    )
    if preflight.status != "ready" or protocol is None:
        raise DataIntegrityError(f"Frozen protocol is blocked: {preflight.blocker}")
    run_path = confirmatory / "run.json"
    run = _validate_confirmatory_run(run_path, protocol, manifest)
    _require_matching_runner(run, runner)
    assignments, _ = _load_frozen_assignments(split, split_report, manifest, run_path)
    records = tuple(
        sorted(
            (record for record in read_manifest(manifest) if record.is_valid),
            key=lambda record: record.sample_id,
        )
    )
    if len(records) != EXPECTED_VALID_ROWS or set(assignments) != {
        record.sample_id for record in records
    }:
        raise DataIntegrityError("Diagnostic assignment does not cover all 514 valid rows")
    eligible = _eligible_ids(records, assignments)
    eligible_categories = {record.category for record in records if record.sample_id in eligible}
    if len(eligible) != EXPECTED_SEEN_ROWS or len(eligible_categories) != EXPECTED_SEEN_CATEGORIES:
        raise DataIntegrityError("Frozen diagnostic no longer has the expected 511/31 estimand")

    recorded_runner = _RecordedRunner(str(run["runner_fingerprint"]))
    source_tasks = tuple(
        task
        for task in build_outer_tasks(protocol, confirmatory, recorded_runner)
        if task.workload == PRIMARY_WORKLOAD
    )
    if len(source_tasks) != FOLD_COUNT or {task.outer_fold for task in source_tasks} != set(
        range(FOLD_COUNT)
    ):
        raise DataIntegrityError("Exactly five inner-selected primary recipes are required")
    dataset_verification = verify_dataset_root(manifest, dataset_root)
    return DiagnosticContext(
        protocol=protocol,
        confirmatory_run=run,
        records=records,
        assignments=assignments,
        source_tasks=tuple(sorted(source_tasks, key=lambda task: int(task.outer_fold or 0))),
        dataset_verification=dataset_verification,
        split_path=split,
        split_report_path=split_report,
        confirmatory_directory=confirmatory,
    )


def _partition(
    context: DiagnosticContext, fold: int
) -> tuple[list[ManifestRecord], list[ManifestRecord]]:
    training = [
        record for record in context.records if context.assignments[record.sample_id] != fold
    ]
    evaluation = [
        record for record in context.records if context.assignments[record.sample_id] == fold
    ]
    if set(record.sample_id for record in training) & set(
        record.sample_id for record in evaluation
    ):
        raise DataIntegrityError("Diagnostic training/evaluation partitions overlap")
    if len(training) + len(evaluation) != len(context.records):
        raise DataIntegrityError("Diagnostic partition does not cover all valid rows")
    return training, evaluation


def _source_task_for_fold(context: DiagnosticContext, fold: int) -> ExperimentTask:
    matches = [task for task in context.source_tasks if task.outer_fold == fold]
    if len(matches) != 1:
        raise DataIntegrityError(f"Missing unique source recipe for diagnostic fold {fold}")
    return matches[0]


def _task_spec(context: DiagnosticContext, fold: int) -> dict[str, Any]:
    training, evaluation = _partition(context, fold)
    source = _source_task_for_fold(context, fold)
    training_categories = {record.category for record in training}
    selection = context.confirmatory_directory / "selections" / f"outer-{fold}.json"
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": f"same-category.fold-{fold}.paired_mobilenet",
        "stage": "secondary_same_category_fit",
        "workload": PRIMARY_WORKLOAD,
        "diagnostic_fold": fold,
        "split_id": FROZEN_SPLIT_ID,
        "training_count": len(training),
        "prediction_count": len(evaluation),
        "seen_category_prediction_count": sum(
            record.category in training_categories for record in evaluation
        ),
        "training_sample_ids_sha256": _canonical_sha256([record.sample_id for record in training]),
        "evaluation_sample_ids_sha256": _canonical_sha256(
            [record.sample_id for record in evaluation]
        ),
        "source_outer_task_spec_sha256": _canonical_sha256(source.to_dict()),
        "source_selection_sha256": sha256_file(selection),
        "parameters": source.parameters,
        "interval_handling": "raw_quantiles_recorded_but_not_calibrated_or_claimed",
    }


def _run_descriptor(context: DiagnosticContext, runner: ProductionTaskRunner) -> dict[str, Any]:
    tasks = [_task_spec(context, fold) for fold in range(FOLD_COUNT)]
    module_path = Path(__file__)
    core = {
        "schema_version": SCHEMA_VERSION,
        "kind": DIAGNOSTIC_KIND,
        "purpose": "secondary diagnostic only; never replaces the category-disjoint primary result",
        "confirmatory_protocol_id": context.protocol.protocol_id,
        "confirmatory_run_id": context.confirmatory_run["run_id"],
        "confirmatory_runner_fingerprint": context.confirmatory_run["runner_fingerprint"],
        "diagnostic_runner_fingerprint": runner.fingerprint,
        "runner_environment": runner.environment,
        "dataset_verification": context.dataset_verification,
        "split": {
            "path": context.split_path.as_posix(),
            "sha256": sha256_file(context.split_path),
            "split_id": FROZEN_SPLIT_ID,
            "freeze_report_path": context.split_report_path.as_posix(),
            "freeze_report_sha256": sha256_file(context.split_report_path),
        },
        "implementation": {
            # Public evidence records a repository-relative locator. The hash
            # binds the executed bytes without exposing a build-host path.
            "path": IMPLEMENTATION_SOURCE_PATH.as_posix(),
            "sha256": sha256_file(module_path),
        },
        "tasks_sha256": _canonical_sha256(tasks),
        "metric_policy": {
            "all_row_context": "514 rows / 34 categories; mixed because three categories are unseen",
            "same_category_estimand": "511 rows / 31 categories seen in training",
            "gap": "category_disjoint_macro_mae_minus_same_category_macro_mae",
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "decision_role": "context_only_no_release_gate",
        },
    }
    return core | {"run_id": _canonical_sha256(core)}


def preflight_same_category_diagnostic(
    **kwargs: Any,
) -> dict[str, Any]:
    runner = kwargs.pop("runner")
    if not isinstance(runner, ProductionTaskRunner):
        raise TypeError("Diagnostic preflight requires ProductionTaskRunner")
    context = load_diagnostic_context(runner=runner, **kwargs)
    descriptor = _run_descriptor(context, runner)
    eligible = _eligible_ids(context.records, context.assignments)
    return {
        "status": "ready",
        "kind": DIAGNOSTIC_KIND,
        "run_id": descriptor["run_id"],
        "split_id": FROZEN_SPLIT_ID,
        "valid_rows": len(context.records),
        "same_category_estimand_rows": len(eligible),
        "same_category_estimand_categories": len(
            {record.category for record in context.records if record.sample_id in eligible}
        ),
        "planned_tasks": FOLD_COUNT,
        "outer_results_read": False,
    }


def _initialize_output(directory: Path, descriptor: dict[str, Any]) -> None:
    run_path = directory / "run.json"
    if run_path.exists():
        if _canonical_json_bytes(_read_json_object(run_path)) != _canonical_json_bytes(descriptor):
            raise DataIntegrityError("Diagnostic run identity changed; use a new directory")
        return
    if directory.exists() and any(directory.iterdir()):
        raise DataIntegrityError("Diagnostic output is non-empty but has no run identity")
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(run_path, descriptor)


def _write_predictions(path: Path, predictions: list[DiagnosticPrediction]) -> None:
    if len({prediction.sample_id for prediction in predictions}) != len(predictions):
        raise DataIntegrityError("Diagnostic predictions repeat a sample ID")
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=DIAGNOSTIC_PREDICTION_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(
            prediction.to_row()
            for prediction in sorted(predictions, key=lambda item: item.sample_id)
        )


def _read_predictions(path: Path) -> list[DiagnosticPrediction]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != DIAGNOSTIC_PREDICTION_FIELDS:
                raise DataIntegrityError("Diagnostic prediction columns differ from schema")
            predictions: list[DiagnosticPrediction] = []
            for row in reader:
                seen_token = row["category_seen_in_training"]
                if seen_token not in {"true", "false"}:
                    raise DataIntegrityError("category_seen_in_training must be 'true' or 'false'")
                predictions.append(
                    DiagnosticPrediction(
                        sample_id=row["sample_id"],
                        category=row["category"],
                        diagnostic_fold=int(row["diagnostic_fold"]),
                        target=float(row["target"]),
                        raw_q05=float(row["raw_q05"]),
                        raw_q50=float(row["raw_q50"]),
                        raw_q95=float(row["raw_q95"]),
                        configuration=row["configuration"],
                        epoch=int(row["epoch"]),
                        category_seen_in_training=seen_token == "true",
                    )
                )
    except (OSError, csv.Error, KeyError, ValueError) as exc:
        raise DataIntegrityError(f"Cannot read diagnostic predictions {path}: {exc}") from exc
    if len({prediction.sample_id for prediction in predictions}) != len(predictions):
        raise DataIntegrityError("Diagnostic predictions repeat a sample ID")
    return predictions


def _validate_predictions(
    context: DiagnosticContext,
    task: dict[str, Any],
    predictions: list[DiagnosticPrediction],
) -> dict[str, Any]:
    fold = int(task["diagnostic_fold"])
    training, evaluation = _partition(context, fold)
    expected_by_id = {record.sample_id: record for record in evaluation}
    expected_ids = sorted(expected_by_id)
    if [prediction.sample_id for prediction in predictions] != expected_ids:
        raise DataIntegrityError("Diagnostic predictions do not cover the fold in stable order")
    training_categories = {record.category for record in training}
    parameters = task["parameters"]
    configuration = str(parameters["configuration"])
    epoch = int(parameters["epoch"])
    for prediction in predictions:
        source = expected_by_id[prediction.sample_id]
        if (
            prediction.category != source.category
            or prediction.diagnostic_fold != fold
            or not math.isclose(
                prediction.target, source.leftover_fraction, rel_tol=0.0, abs_tol=1e-12
            )
            or prediction.configuration != configuration
            or prediction.epoch != epoch
            or prediction.category_seen_in_training != (source.category in training_categories)
        ):
            raise DataIntegrityError(
                f"Diagnostic prediction metadata differs for {prediction.sample_id}"
            )
    targets = np.asarray([prediction.target for prediction in predictions])
    values = np.asarray([prediction.raw_q50 for prediction in predictions])
    categories = np.asarray([prediction.category for prediction in predictions])
    seen = np.asarray(
        [prediction.category_seen_in_training for prediction in predictions], dtype=bool
    )
    if not np.any(seen):
        raise DataIntegrityError("Diagnostic fold has no seen-category observations")
    return {
        "training_count": len(training),
        "prediction_count": len(evaluation),
        "seen_category_prediction_count": int(np.sum(seen)),
        "fold_macro_category_mae_all_rows": macro_category_mae(targets, values, categories),
        "fold_macro_category_mae_seen_categories": macro_category_mae(
            targets[seen], values[seen], categories[seen]
        ),
        "interval_status": "raw_uncalibrated_not_for_coverage_or_public_interval_claims",
    }


def _fit_predict(
    source_task: ExperimentTask,
    training: list[ManifestRecord],
    evaluation: list[ManifestRecord],
    *,
    dataset_root: Path,
    runner: ProductionTaskRunner,
) -> np.ndarray:  # pragma: no cover - optional heavy runtime
    from .training import PairedImageDataset
    from .workloads import (
        _build_neural_model,
        _fit_fixed_epochs,
        _predict_neural,
        _require_torch,
    )

    torch, DataLoader = _require_torch()
    parameters = source_task.parameters
    model, after_only, configuration = _build_neural_model(source_task, runner.checkpoint_root)
    if after_only:
        raise DataIntegrityError("Same-category diagnostic requires the paired model")
    train_dataset = PairedImageDataset(
        training, dataset_root, training=True, seed=int(parameters["seed"])
    )
    evaluation_dataset = PairedImageDataset(
        evaluation, dataset_root, training=False, seed=int(parameters["seed"])
    )
    generator = torch.Generator().manual_seed(int(parameters["seed"]))
    train_loader = DataLoader(
        train_dataset,
        batch_size=int(parameters["batch_size"]),
        shuffle=True,
        num_workers=0,
        generator=generator,
    )
    evaluation_loader = DataLoader(
        evaluation_dataset,
        batch_size=int(parameters["batch_size"]),
        shuffle=False,
        num_workers=0,
    )
    _fit_fixed_epochs(
        model,
        train_loader,
        configuration,
        parameters,
        device=runner.device,
        after_only=False,
    )
    sample_ids, quantiles = _predict_neural(
        model, evaluation_loader, device=runner.device, after_only=False
    )
    if sample_ids != [record.sample_id for record in evaluation]:
        raise DataIntegrityError("Diagnostic model prediction order changed")
    values = np.asarray(quantiles, dtype=np.float64)
    if (
        values.shape != (len(evaluation), 3)
        or not np.isfinite(values).all()
        or np.any(values < 0.0)
        or np.any(values > 1.0)
        or np.any(np.diff(values, axis=1) < 0.0)
    ):
        raise DataIntegrityError("Diagnostic model emitted invalid raw quantiles")
    return values


def _task_directory(output: Path, task: dict[str, Any]) -> Path:
    return output / "tasks" / str(task["task_id"])


def _validate_completed_task(
    context: DiagnosticContext,
    output: Path,
    descriptor: dict[str, Any],
    task: dict[str, Any],
) -> tuple[dict[str, Any], list[DiagnosticPrediction]]:
    directory = _task_directory(output, task)
    observed_task = _strict_json_object(directory / "task.json")
    if _canonical_json_bytes(observed_task) != _canonical_json_bytes(task):
        raise DataIntegrityError(f"Diagnostic task specification changed: {task['task_id']}")
    result = _strict_json_object(directory / "result.json")
    expected_result_fields = {
        "schema_version",
        "status",
        "task_id",
        "run_id",
        "task_spec_sha256",
        "runner_fingerprint",
        "payload",
        "payload_sha256",
        "artifacts",
    }
    if set(result) != expected_result_fields:
        raise DataIntegrityError(f"Diagnostic result fields changed: {task['task_id']}")
    expected_identity = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "task_id": task["task_id"],
        "run_id": descriptor["run_id"],
        "task_spec_sha256": _canonical_sha256(task),
        "runner_fingerprint": descriptor["diagnostic_runner_fingerprint"],
    }
    if any(result.get(key) != value for key, value in expected_identity.items()):
        raise DataIntegrityError(f"Diagnostic result identity changed: {task['task_id']}")
    payload = result.get("payload")
    artifacts = result.get("artifacts")
    if (
        not isinstance(payload, dict)
        or result.get("payload_sha256") != _canonical_sha256(payload)
        or not isinstance(artifacts, list)
        or len(artifacts) != 1
    ):
        raise DataIntegrityError(f"Malformed diagnostic result: {task['task_id']}")
    item = artifacts[0]
    if (
        not isinstance(item, dict)
        or set(item) != {"role", "path", "size_bytes", "sha256"}
        or item.get("role") != "predictions"
    ):
        raise DataIntegrityError("Diagnostic task requires one predictions artifact")
    relative = _safe_relative_artifact(str(item.get("path", "")))
    path = directory / relative
    if (
        not path.is_file()
        or path.is_symlink()
        or item.get("size_bytes") != path.stat().st_size
        or item.get("sha256") != sha256_file(path)
    ):
        raise DataIntegrityError("Diagnostic predictions hash/size mismatch")
    actual_files = {
        candidate.relative_to(directory)
        for candidate in (directory / "workload").rglob("*")
        if candidate.is_file()
    }
    if actual_files != {relative}:
        raise DataIntegrityError("Diagnostic task has undeclared or missing artifacts")
    predictions = _read_predictions(path)
    expected_payload = _validate_predictions(context, task, predictions)
    if _canonical_json_bytes(payload) != _canonical_json_bytes(expected_payload):
        raise DataIntegrityError("Diagnostic task payload differs from its predictions")
    return payload, predictions


def _execute_task(
    context: DiagnosticContext,
    output: Path,
    descriptor: dict[str, Any],
    task: dict[str, Any],
    runner: ProductionTaskRunner,
    dataset_root: Path,
) -> bool:
    directory = _task_directory(output, task)
    if directory.exists():
        _validate_completed_task(context, output, descriptor, task)
        return False
    attempts = output / ".attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    fold = int(task["diagnostic_fold"])
    training, evaluation = _partition(context, fold)
    source = _source_task_for_fold(context, fold)
    with tempfile.TemporaryDirectory(prefix=f"fold-{fold}.", dir=attempts) as temporary:
        staging = Path(temporary)
        workspace = staging / "workload"
        workspace.mkdir()
        quantiles = _fit_predict(
            source,
            training,
            evaluation,
            dataset_root=dataset_root,
            runner=runner,
        )
        training_categories = {record.category for record in training}
        predictions = [
            DiagnosticPrediction(
                sample_id=record.sample_id,
                category=record.category,
                diagnostic_fold=fold,
                target=record.leftover_fraction,
                raw_q05=float(row[0]),
                raw_q50=float(row[1]),
                raw_q95=float(row[2]),
                configuration=str(source.parameters["configuration"]),
                epoch=int(source.parameters["epoch"]),
                category_seen_in_training=record.category in training_categories,
            )
            for record, row in zip(evaluation, quantiles, strict=True)
        ]
        prediction_path = workspace / "predictions.csv"
        _write_predictions(prediction_path, predictions)
        payload = _validate_predictions(context, task, predictions)
        inventory = _artifact_inventory(
            workspace, WorkloadResult(payload=payload, artifacts={"predictions": "predictions.csv"})
        )
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "complete",
            "task_id": task["task_id"],
            "run_id": descriptor["run_id"],
            "task_spec_sha256": _canonical_sha256(task),
            "runner_fingerprint": descriptor["diagnostic_runner_fingerprint"],
            "payload": payload,
            "payload_sha256": _canonical_sha256(payload),
            "artifacts": inventory,
        }
        _atomic_write_json(staging / "task.json", task)
        _atomic_write_json(staging / "result.json", result)
        if directory.exists():
            raise DataIntegrityError(f"Diagnostic task completed concurrently: {task['task_id']}")
        directory.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(directory)
    return True


def fit_same_category_diagnostic(
    *,
    runner: ProductionTaskRunner,
    output_directory: str | Path = DEFAULT_DIAGNOSTIC_DIRECTORY,
    dataset_root: str | Path = DEFAULT_DATASET_ROOT,
    **kwargs: Any,
) -> dict[str, Any]:
    """Fit five immutable diagnostic tasks without opening outer outcomes."""

    context = load_diagnostic_context(runner=runner, dataset_root=dataset_root, **kwargs)
    descriptor = _run_descriptor(context, runner)
    output = Path(output_directory)
    _initialize_output(output, descriptor)
    executed = resumed = 0
    for fold in range(FOLD_COUNT):
        task = _task_spec(context, fold)
        if _execute_task(
            context,
            output,
            descriptor,
            task,
            runner,
            Path(dataset_root),
        ):
            executed += 1
        else:
            resumed += 1
    return {
        "status": "complete",
        "stage": "fit",
        "run_id": descriptor["run_id"],
        "planned_tasks": FOLD_COUNT,
        "executed_tasks": executed,
        "resumed_tasks": resumed,
        "outer_results_read": False,
        "output_directory": output.as_posix(),
    }


def _validated_primary_predictions(
    context: DiagnosticContext,
) -> tuple[list[Any], list[dict[str, str]]]:
    """Open only validated primary outer predictions during aggregate stage."""

    from .post_evaluation import _load_outer_task

    manifest_by_id = {record.sample_id: record for record in context.records}
    predictions: list[Any] = []
    sources: list[dict[str, str]] = []
    for task in context.source_tasks:
        loaded = _load_outer_task(
            context.confirmatory_directory,
            task,
            protocol_id=context.protocol.protocol_id,
            runner_fingerprint=str(context.confirmatory_run["runner_fingerprint"]),
            manifest_by_id=manifest_by_id,
        )
        predictions.extend(loaded.predictions)
        sources.append(
            {
                "task_id": task.task_id,
                "result_sha256": sha256_file(loaded.result_path),
                "predictions_sha256": sha256_file(loaded.prediction_path),
            }
        )
    predictions.sort(key=lambda prediction: str(prediction.sample_id))
    if (
        len(predictions) != EXPECTED_VALID_ROWS
        or len({prediction.sample_id for prediction in predictions}) != EXPECTED_VALID_ROWS
    ):
        raise DataIntegrityError("Validated primary predictions do not cover 514 rows")
    return predictions, sources


def build_summary_payload(
    context: DiagnosticContext,
    diagnostic_predictions: list[DiagnosticPrediction],
    primary_predictions: list[Any],
    *,
    run_id: str,
    diagnostic_sources: list[dict[str, str]],
    primary_sources: list[dict[str, str]],
) -> dict[str, Any]:
    """Build the context-only, matched 511-row diagnostic report."""

    diagnostic_by_id = {prediction.sample_id: prediction for prediction in diagnostic_predictions}
    primary_by_id = {str(prediction.sample_id): prediction for prediction in primary_predictions}
    expected_ids = {record.sample_id for record in context.records}
    if set(diagnostic_by_id) != expected_ids or set(primary_by_id) != expected_ids:
        raise DataIntegrityError("Diagnostic and primary reports must cover identical 514 rows")
    eligible = _eligible_ids(context.records, context.assignments)
    ineligible = tuple(sorted(expected_ids.difference(eligible)))
    if len(eligible) != EXPECTED_SEEN_ROWS:
        raise DataIntegrityError("Same-category estimand must contain exactly 511 rows")
    ordered_all = sorted(expected_ids)
    all_targets = np.asarray([diagnostic_by_id[sample_id].target for sample_id in ordered_all])
    all_values = np.asarray([diagnostic_by_id[sample_id].raw_q50 for sample_id in ordered_all])
    all_categories = np.asarray([diagnostic_by_id[sample_id].category for sample_id in ordered_all])
    targets = np.asarray([diagnostic_by_id[sample_id].target for sample_id in eligible])
    same_values = np.asarray([diagnostic_by_id[sample_id].raw_q50 for sample_id in eligible])
    primary_values = np.asarray([float(primary_by_id[sample_id].q50) for sample_id in eligible])
    categories = np.asarray([diagnostic_by_id[sample_id].category for sample_id in eligible])
    for sample_id in ordered_all:
        primary = primary_by_id[sample_id]
        diagnostic = diagnostic_by_id[sample_id]
        if str(primary.category) != diagnostic.category or not math.isclose(
            float(primary.target), diagnostic.target, rel_tol=0.0, abs_tol=1e-12
        ):
            raise DataIntegrityError(f"Primary/diagnostic row mismatch for {sample_id}")
    if len(np.unique(categories)) != EXPECTED_SEEN_CATEGORIES:
        raise DataIntegrityError("Same-category estimand must contain exactly 31 categories")
    same_metrics = regression_metrics(targets, same_values, categories).to_dict()
    primary_metrics = regression_metrics(targets, primary_values, categories).to_dict()
    bootstrap = category_bootstrap_mae_difference(
        targets,
        primary_values,
        same_values,
        categories,
        replicates=BOOTSTRAP_REPLICATES,
        seed=BOOTSTRAP_SEED,
    ).to_dict()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": DIAGNOSTIC_KIND,
        "status": "complete",
        "run_id": run_id,
        "split_id": FROZEN_SPLIT_ID,
        "decision_role": "context_only_no_release_gate",
        "interval_status": "raw_quantiles_not_calibrated_or_evaluated_for_interval_claims",
        "coverage": {
            "all_rows": len(ordered_all),
            "all_categories": len(np.unique(all_categories)),
            "seen_category_rows": len(eligible),
            "seen_categories": len(np.unique(categories)),
            "unseen_category_rows": len(ineligible),
            "unseen_sample_ids": list(ineligible),
        },
        "all_row_mixed_context": regression_metrics(
            all_targets, all_values, all_categories
        ).to_dict(),
        "matched_seen_category_estimand": {
            "same_category": same_metrics,
            "category_disjoint_primary": primary_metrics,
            "observed_gap_category_disjoint_minus_same_category": (
                float(primary_metrics["macro_category_mae"])
                - float(same_metrics["macro_category_mae"])
            ),
            "paired_category_bootstrap_primary_minus_same_category": bootstrap,
        },
        "interpretation": {
            "positive_gap": "category-disjoint evaluation had higher macro-category MAE",
            "scope": (
                "Observed CV performance gap under the matched five-recipe protocol; "
                "not a causal estimate and not a replacement for the primary result."
            ),
            "recipe_caveat": (
                "The same five fold-index recipes are reused, but an individual sample may "
                "be scored under a different fold recipe across regimes."
            ),
        },
        "sources": {
            "diagnostic_tasks": sorted(diagnostic_sources, key=lambda item: item["task_id"]),
            "confirmatory_primary_tasks": sorted(primary_sources, key=lambda item: item["task_id"]),
        },
    }


def aggregate_same_category_diagnostic(
    *,
    runner: ProductionTaskRunner,
    output_directory: str | Path = DEFAULT_DIAGNOSTIC_DIRECTORY,
    dataset_root: str | Path = DEFAULT_DATASET_ROOT,
    **kwargs: Any,
) -> dict[str, Any]:
    """Validate all five tasks, then open primary outer predictions once."""

    context = load_diagnostic_context(runner=runner, dataset_root=dataset_root, **kwargs)
    descriptor = _run_descriptor(context, runner)
    output = Path(output_directory)
    _initialize_output(output, descriptor)
    diagnostic_predictions: list[DiagnosticPrediction] = []
    diagnostic_sources: list[dict[str, str]] = []
    for fold in range(FOLD_COUNT):
        task = _task_spec(context, fold)
        _, predictions = _validate_completed_task(context, output, descriptor, task)
        directory = _task_directory(output, task)
        diagnostic_predictions.extend(predictions)
        diagnostic_sources.append(
            {
                "task_id": str(task["task_id"]),
                "result_sha256": sha256_file(directory / "result.json"),
                "predictions_sha256": sha256_file(directory / "workload" / "predictions.csv"),
            }
        )
    diagnostic_predictions.sort(key=lambda prediction: prediction.sample_id)
    primary_predictions, primary_sources = _validated_primary_predictions(context)
    summary = build_summary_payload(
        context,
        diagnostic_predictions,
        primary_predictions,
        run_id=str(descriptor["run_id"]),
        diagnostic_sources=diagnostic_sources,
        primary_sources=primary_sources,
    )
    summary_path = output / "summary.json"
    _write_or_validate_json(summary_path, summary)
    return {
        "status": "complete",
        "stage": "aggregate",
        "run_id": descriptor["run_id"],
        "summary_path": summary_path.as_posix(),
        "summary_sha256": sha256_file(summary_path),
        "decision_role": "context_only_no_release_gate",
    }


__all__ = [
    "DEFAULT_DIAGNOSTIC_DIRECTORY",
    "DEFAULT_SPLIT_CONFIG",
    "DEFAULT_SPLIT_REPORT",
    "DiagnosticPrediction",
    "aggregate_same_category_diagnostic",
    "build_summary_payload",
    "fit_same_category_diagnostic",
    "load_diagnostic_context",
    "preflight_same_category_diagnostic",
]
