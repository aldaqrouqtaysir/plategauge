"""Exploratory sensitivity analysis for visually discordant benchmark records.

This module is intentionally separate from the frozen confirmatory aggregation.
It never changes the dataset, predictions, or confirmatory results.  It answers
one post-hoc question only: does removing a declared set of visually discordant
records reverse the paired-versus-after-only conclusion?
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .data import sha256_file
from .errors import DataIntegrityError
from .evaluation import PredictionRecord, read_predictions
from .metrics import regression_metrics
from .post_evaluation import _canonical_sha256, _immutable_json_write

SCHEMA_VERSION = "1.0"
EXPECTED_PAIRS = 514
EXPECTED_FOLDS = frozenset(range(5))


def _load_workload(directory: Path, workload: str) -> tuple[list[PredictionRecord], list[dict[str, str]]]:
    records: list[PredictionRecord] = []
    sources: list[dict[str, str]] = []
    for fold in sorted(EXPECTED_FOLDS):
        path = (
            directory
            / "tasks"
            / f"outer.fold-{fold}.{workload}"
            / "workload"
            / "predictions.csv"
        )
        if not path.is_file() or path.is_symlink():
            raise DataIntegrityError(f"Missing regular prediction artifact: {path}")
        fold_records = read_predictions(path)
        if not fold_records or {record.outer_fold for record in fold_records} != {fold}:
            raise DataIntegrityError(f"Prediction artifact has the wrong outer fold: {path}")
        if {record.workload for record in fold_records} != {workload}:
            raise DataIntegrityError(f"Prediction artifact has the wrong workload: {path}")
        records.extend(fold_records)
        sources.append(
            {
                "outer_fold": str(fold),
                "path": path.relative_to(directory).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    ids = [record.sample_id for record in records]
    if len(records) != EXPECTED_PAIRS or len(set(ids)) != EXPECTED_PAIRS:
        raise DataIntegrityError(
            f"{workload} must contain {EXPECTED_PAIRS} unique outer predictions"
        )
    return records, sources


def _metrics(records: Iterable[PredictionRecord]) -> dict[str, Any]:
    rows = list(records)
    if not rows:
        raise DataIntegrityError("Sensitivity subset cannot be empty")
    return regression_metrics(
        [record.target for record in rows],
        [record.q50 for record in rows],
        [record.category for record in rows],
    ).to_dict()


def build_label_sensitivity_report(
    *,
    run_directory: str | Path,
    excluded_sample_ids: Iterable[str],
    output_path: str | Path,
) -> dict[str, Any]:
    """Build one immutable, explicitly post-hoc sensitivity report."""

    run_dir = Path(run_directory)
    excluded = tuple(sorted(set(excluded_sample_ids)))
    if not excluded:
        raise DataIntegrityError("At least one declared sample ID is required")

    paired, paired_sources = _load_workload(run_dir, "paired_mobilenet")
    after_only, after_sources = _load_workload(run_dir, "after_only_mobilenet")
    paired_by_id = {record.sample_id: record for record in paired}
    after_by_id = {record.sample_id: record for record in after_only}
    if paired_by_id.keys() != after_by_id.keys():
        raise DataIntegrityError("Paired and after-only prediction IDs differ")
    missing = sorted(set(excluded) - paired_by_id.keys())
    if missing:
        raise DataIntegrityError(f"Unknown declared sample IDs: {missing}")
    for sample_id in paired_by_id:
        first, second = paired_by_id[sample_id], after_by_id[sample_id]
        if (
            first.category != second.category
            or first.outer_fold != second.outer_fold
            or first.target != second.target
        ):
            raise DataIntegrityError(f"Prediction rows do not align for {sample_id}")

    retained_ids = paired_by_id.keys() - set(excluded)
    paired_retained = [paired_by_id[sample_id] for sample_id in sorted(retained_ids)]
    after_retained = [after_by_id[sample_id] for sample_id in sorted(retained_ids)]
    original_paired = _metrics(paired)
    original_after = _metrics(after_only)
    sensitivity_paired = _metrics(paired_retained)
    sensitivity_after = _metrics(after_retained)
    original_gap = (
        float(original_paired["macro_category_mae"])
        - float(original_after["macro_category_mae"])
    )
    sensitivity_gap = (
        float(sensitivity_paired["macro_category_mae"])
        - float(sensitivity_after["macro_category_mae"])
    )

    core: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "posthoc_visual_discordance_sensitivity",
        "status": "complete",
        "confirmatory": False,
        "changes_frozen_results": False,
        "interpretation": (
            "The exclusions were chosen after visual review and cannot support a new "
            "confirmatory estimate. They test only whether the central paired-versus-"
            "after-only direction reverses under this declared omission."
        ),
        "excluded_sample_ids": list(excluded),
        "excluded_count": len(excluded),
        "retained_count": len(retained_ids),
        "original": {
            "paired_mobilenet": original_paired,
            "after_only_mobilenet": original_after,
            "paired_minus_after_only_macro_category_mae": original_gap,
        },
        "sensitivity_after_exclusion": {
            "paired_mobilenet": sensitivity_paired,
            "after_only_mobilenet": sensitivity_after,
            "paired_minus_after_only_macro_category_mae": sensitivity_gap,
        },
        "conclusion": {
            "paired_still_worse_than_after_only": sensitivity_gap > 0.0,
            "direction_reversed": (original_gap > 0.0) != (sensitivity_gap > 0.0),
        },
        "sources": {
            "paired_mobilenet": paired_sources,
            "after_only_mobilenet": after_sources,
            "analysis_code_path": "src/plategauge/label_sensitivity.py",
            "analysis_code_sha256": sha256_file(Path(__file__)),
        },
    }
    report = core | {"evidence_sha256": _canonical_sha256(core)}
    _immutable_json_write(Path(output_path), report)
    return report
