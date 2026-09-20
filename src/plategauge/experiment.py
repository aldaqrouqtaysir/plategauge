"""Guarded end-to-end experiment orchestration contract.

No model is allowed to train while the machine-readable data audit is red. This
module retains the original audit-only compatibility API; the executable,
immutable staged runner lives in :mod:`plategauge.orchestration` and the CLI.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .folds import EXPECTED_FOLD_COUNTS, inner_folds


@dataclass(frozen=True, slots=True)
class ExperimentPreflight:
    status: str
    blocker: str | None
    audit_report: str
    frozen_outer_folds: int
    inner_runs: tuple[dict[str, Any], ...]
    baselines_and_ablations: tuple[str, ...]
    final_stages: tuple[str, ...]
    planned_outputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def experiment_task_matrix() -> tuple[dict[str, Any], ...]:
    """Return all 40 preregistered M1/M2 inner runs in deterministic order."""

    return tuple(
        {
            "outer_fold": outer,
            "inner_validation_fold": inner,
            "configuration": configuration,
        }
        for outer in range(5)
        for inner in inner_folds(outer)
        for configuration in ("M1", "M2")
    )


def experiment_preflight(audit_report_path: str | Path) -> ExperimentPreflight:
    """Read the frozen audit and report whether any experiment work may start."""

    path = Path(audit_report_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
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
    }
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("Audit report 'issues' must be a list")
    gate_errors = [
        f"{name} must equal {expected!r}, found {payload.get(name)!r}"
        for name, expected in required_values.items()
        if payload.get(name) != expected
    ]
    expected_fold_counts = {str(key): value for key, value in EXPECTED_FOLD_COUNTS.items()}
    if payload.get("fold_counts") != expected_fold_counts:
        gate_errors.append(
            f"fold_counts must equal {expected_fold_counts!r}, found {payload.get('fold_counts')!r}"
        )
    if issues:
        gate_errors.extend(str(issue) for issue in issues)
    if payload.get("passed") is not True:
        gate_errors.append("audit report did not declare passed=true")
    passed = not gate_errors
    blocker = None if passed else "data_gate: " + "; ".join(gate_errors)
    return ExperimentPreflight(
        status="ready" if passed else "blocked",
        blocker=blocker,
        audit_report=path.as_posix(),
        frozen_outer_folds=5,
        inner_runs=experiment_task_matrix(),
        baselines_and_ablations=(
            "training_fold_median",
            "handcrafted_features_ridge_inner_selected_alpha",
            "paired_resnet50_late_fusion",
            "after_only_mobilenetv3",
            "frozen_paired_dinov2_small_head",
            "fixed_within_category_wrong_pair",
            "observer_score_context_only",
        ),
        final_stages=(
            "select M1/M2 per outer fold by mean inner macro-category MAE",
            "select epoch as median inner best epoch",
            "retrain on four development folds and open outer fold once",
            "aggregate 514 unique outer predictions",
            "derive correction and abstention from inner OOF predictions only",
            "select modal configuration and median epoch for final 514-pair retrain",
            "export ONNX and enforce 1e-4 parity gate",
        ),
        planned_outputs=(
            "reports/predictions/outer_predictions.csv",
            "reports/predictions/inner_oof_predictions.csv",
            "reports/results.json",
            "reports/bootstrap_comparisons.json",
            "reports/robustness.json",
            "artifacts/plategauge.onnx",
            "artifacts/plategauge.onnx.json",
        ),
    )


def run_experiment(audit_report_path: str | Path, *, dry_run: bool = False) -> ExperimentPreflight:
    """Run the legacy audit-only gate without silently starting model fitting."""

    preflight = experiment_preflight(audit_report_path)
    if preflight.status != "ready":
        return preflight
    if dry_run:
        return preflight
    raise RuntimeError(
        "This compatibility API is preflight-only. Use the run-experiment CLI with an explicit "
        "--stage and the approved production runner to execute the frozen protocol."
    )
