"""Deterministic, read-only derivation of the frozen Gate C error ledger.

The derivation reuses the confirmatory runner's fail-closed artifact validators
but never loads a model, executes a workload, or edits a prediction/result file.
Visual failure themes are deliberately reserved for a later human review.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .data import sha256_file
from .errors import DataIntegrityError
from .evaluation import PredictionRecord
from .folds import EXPECTED_FOLD_COUNTS, EXPECTED_VALID_COUNTS
from .metrics import regression_metrics
from .orchestration import PRIMARY_WORKLOAD, build_outer_tasks, protocol_preflight
from .post_evaluation import (
    _canonical_sha256,
    _immutable_json_write,
    _load_outer_task,
    _RecordedRunner,
    _validate_run_descriptor,
)
from .schema import ManifestRecord, read_manifest

ERROR_ANALYSIS_SCHEMA_VERSION = "1.0"
EXPECTED_VALID_PAIRS = 514
TAIL_SIZE = 20
MANUAL_REVIEW_PENDING = "pending_manual_review"

PREDEFINED_FAILURE_THEMES: tuple[str, ...] = (
    "OIL_OR_SAUCE_RESIDUE",
    "LOW_CONTRAST_RICE_OR_PORRIDGE",
    "GLARE_OR_SPECULARITY",
    "PAIR_MISALIGNMENT",
    "CONTENT_CROPPED",
    "BOUNDARY_TARGET_ZERO",
    "BOUNDARY_TARGET_ONE",
    "BACKGROUND_OR_CONTAINER_CHANGE",
    "OTHER_POSTHOC",
)


def _require_regular_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise DataIntegrityError(f"{label} must be a regular file: {path}")


def _manual_review_fields() -> dict[str, Any]:
    return {
        "status": MANUAL_REVIEW_PENDING,
        "theme_assessments": {
            theme: MANUAL_REVIEW_PENDING for theme in PREDEFINED_FAILURE_THEMES
        },
        "other_posthoc_definition": MANUAL_REVIEW_PENDING,
        "review_notes": MANUAL_REVIEW_PENDING,
    }


def _row(
    rank: int,
    prediction: PredictionRecord,
    *,
    retained_ids: set[str],
) -> dict[str, Any]:
    signed_error = prediction.q50 - prediction.target
    return {
        "rank": rank,
        "sample_id": prediction.sample_id,
        "category": prediction.category,
        "outer_fold": prediction.outer_fold,
        "target": prediction.target,
        "q05": prediction.q05,
        "q50": prediction.q50,
        "q95": prediction.q95,
        "signed_error_q50_minus_target": signed_error,
        "absolute_error": abs(signed_error),
        "interval_width": prediction.q95 - prediction.q05,
        "interval_contains_target": prediction.q05
        <= prediction.target
        <= prediction.q95,
        "retained_by_frozen_width_rule": prediction.sample_id in retained_ids,
        "configuration": prediction.configuration,
        "epoch": prediction.epoch,
        "failure_theme_review": _manual_review_fields(),
    }


def _tail_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    errors = [float(row["absolute_error"]) for row in rows]
    return {
        "count": len(rows),
        "category_count": len({str(row["category"]) for row in rows}),
        "mean_absolute_error": math.fsum(errors) / len(errors),
        "median_absolute_error": statistics.median(errors),
        "minimum_absolute_error": min(errors),
        "maximum_absolute_error": max(errors),
    }


def _selection_sources(run_directory: Path) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for fold in range(5):
        relative = Path("selections") / f"outer-{fold}.json"
        path = run_directory / relative
        _require_regular_file(path, f"Outer-fold {fold} selection")
        sources.append(
            {
                "outer_fold": fold,
                "path": relative.as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return sources


def build_error_analysis_report(
    *,
    run_directory: str | Path,
    manifest_path: str | Path,
    audit_report_path: str | Path,
    config_path: str | Path,
    folds_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen primary outer predictions and write one immutable report."""

    run_dir = Path(run_directory)
    manifest_file = Path(manifest_path)
    _require_regular_file(manifest_file, "Manifest")
    manifest_records = read_manifest(manifest_file)
    valid_records = [record for record in manifest_records if record.is_valid]
    if len(valid_records) != EXPECTED_VALID_PAIRS:
        raise DataIntegrityError(
            f"Error analysis requires {EXPECTED_VALID_PAIRS} valid pairs, "
            f"found {len(valid_records)}"
        )
    category_counts = dict(sorted(Counter(record.category for record in valid_records).items()))
    if category_counts != EXPECTED_VALID_COUNTS:
        raise DataIntegrityError("Valid manifest category counts differ from the frozen protocol")
    fold_counts = dict(sorted(Counter(record.outer_fold for record in valid_records).items()))
    if fold_counts != EXPECTED_FOLD_COUNTS:
        raise DataIntegrityError("Valid manifest fold counts differ from the frozen protocol")

    preflight, protocol = protocol_preflight(
        audit_report_path=audit_report_path,
        manifest_path=manifest_file,
        config_path=config_path,
        folds_path=folds_path,
    )
    if preflight.status != "ready" or protocol is None:
        raise DataIntegrityError(f"Frozen protocol preflight is blocked: {preflight.blocker}")

    run_path = run_dir / "run.json"
    run = _validate_run_descriptor(
        run_path,
        protocol_id=protocol.protocol_id,
        manifest_path=manifest_file,
        record_count=len(manifest_records),
    )
    runner_fingerprint = str(run["runner_fingerprint"])
    runner = _RecordedRunner(runner_fingerprint)
    all_outer_tasks = build_outer_tasks(protocol, run_dir, runner)
    primary_tasks = tuple(
        task for task in all_outer_tasks if task.workload == PRIMARY_WORKLOAD
    )
    expected_ids = {
        f"outer.fold-{fold}.{PRIMARY_WORKLOAD}" for fold in range(5)
    }
    if (
        len(primary_tasks) != 5
        or {task.task_id for task in primary_tasks} != expected_ids
        or {task.evaluation_fold for task in primary_tasks} != set(range(5))
    ):
        raise DataIntegrityError(
            "Primary outer task matrix must contain exactly one paired_mobilenet task per fold"
        )

    manifest_by_id: dict[str, ManifestRecord] = {
        record.sample_id: record for record in valid_records
    }
    predictions: list[PredictionRecord] = []
    retained_ids: set[str] = set()
    task_sources: list[dict[str, Any]] = []
    for task in sorted(primary_tasks, key=lambda value: int(value.evaluation_fold or 0)):
        loaded = _load_outer_task(
            run_dir,
            task,
            protocol_id=protocol.protocol_id,
            runner_fingerprint=runner_fingerprint,
            manifest_by_id=manifest_by_id,
        )
        predictions.extend(loaded.predictions)
        retained = loaded.payload.get("retained_sample_ids")
        if not isinstance(retained, list) or not all(
            isinstance(sample_id, str) for sample_id in retained
        ):
            raise DataIntegrityError(
                f"Primary retained IDs are malformed: {task.task_id}"
            )
        retained_ids.update(retained)
        task_directory = run_dir / "tasks" / task.task_id
        task_path = task_directory / "task.json"
        task_sources.append(
            {
                "task_id": task.task_id,
                "outer_fold": task.evaluation_fold,
                "task_path": task_path.relative_to(run_dir).as_posix(),
                "task_sha256": sha256_file(task_path),
                "result_path": loaded.result_path.relative_to(run_dir).as_posix(),
                "result_sha256": sha256_file(loaded.result_path),
                "predictions_path": loaded.prediction_path.relative_to(run_dir).as_posix(),
                "predictions_sha256": sha256_file(loaded.prediction_path),
            }
        )

    observed_ids = [prediction.sample_id for prediction in predictions]
    if (
        len(predictions) != EXPECTED_VALID_PAIRS
        or len(set(observed_ids)) != EXPECTED_VALID_PAIRS
        or set(observed_ids) != set(manifest_by_id)
    ):
        raise DataIntegrityError(
            "Primary outer predictions must cover every valid manifest row exactly once"
        )
    if not retained_ids.issubset(manifest_by_id):
        raise DataIntegrityError("Primary retained IDs include an unknown manifest row")

    by_largest_error = sorted(
        predictions,
        key=lambda record: (-abs(record.q50 - record.target), record.sample_id),
    )
    by_smallest_error = sorted(
        predictions,
        key=lambda record: (abs(record.q50 - record.target), record.sample_id),
    )
    largest_rows = [
        _row(rank, prediction, retained_ids=retained_ids)
        for rank, prediction in enumerate(by_largest_error[:TAIL_SIZE], start=1)
    ]
    smallest_rows = [
        _row(rank, prediction, retained_ids=retained_ids)
        for rank, prediction in enumerate(by_smallest_error[:TAIL_SIZE], start=1)
    ]

    targets = [prediction.target for prediction in predictions]
    point_predictions = [prediction.q50 for prediction in predictions]
    categories = [prediction.category for prediction in predictions]
    source_code = Path(__file__)
    core: dict[str, Any] = {
        "schema_version": ERROR_ANALYSIS_SCHEMA_VERSION,
        "kind": "frozen_primary_outer_error_analysis",
        "status": "complete",
        "frozen": True,
        "run_id": run["run_id"],
        "protocol_id": protocol.protocol_id,
        "dataset": {
            "valid_pairs": len(valid_records),
            "categories": len(category_counts),
            "fold_counts": {str(fold): count for fold, count in fold_counts.items()},
        },
        "analysis_contract": {
            "workload": PRIMARY_WORKLOAD,
            "point_prediction": "q50",
            "ranking_metric": "absolute(q50 - target)",
            "largest_ranking": "absolute_error descending; sample_id ascending breaks ties",
            "smallest_ranking": "absolute_error ascending; sample_id ascending breaks ties",
            "records_per_tail": TAIL_SIZE,
            "visual_review_performed": False,
            "manual_review_status": MANUAL_REVIEW_PENDING,
            "predefined_failure_themes": list(PREDEFINED_FAILURE_THEMES),
            "raw_images_included": False,
            "analysis_code_path": "src/plategauge/error_analysis.py",
            "analysis_code_sha256": sha256_file(source_code),
        },
        "primary_outer_metrics": regression_metrics(
            targets, point_predictions, categories
        ).to_dict(),
        "largest_absolute_errors": {
            "interpretation": "failure_review_candidates",
            "summary": _tail_summary(largest_rows),
            "records": largest_rows,
        },
        "smallest_absolute_errors": {
            "interpretation": "representative_success_candidates",
            "summary": _tail_summary(smallest_rows),
            "records": smallest_rows,
        },
        "source_artifacts": {
            "protocol_input_hashes": dict(sorted(protocol.input_hashes.items())),
            "manifest_sha256": sha256_file(manifest_file),
            "run_descriptor": {
                "path": "run.json",
                "sha256": sha256_file(run_path),
            },
            "outer_selections": _selection_sources(run_dir),
            "paired_mobilenet_outer_tasks": task_sources,
        },
    }
    report = core | {"evidence_sha256": _canonical_sha256(core)}
    _immutable_json_write(Path(output_path), report)
    return report
