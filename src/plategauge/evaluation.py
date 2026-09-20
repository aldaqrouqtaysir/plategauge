"""Prediction-file schema, aggregated evaluation, and acceptance decisions."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .metrics import metrics_by_slice, regression_metrics, target_slice_labels
from .schema import ManifestRecord
from .uncertainty import evaluate_interval_gate

PREDICTION_FIELDS = (
    "sample_id",
    "category",
    "outer_fold",
    "target",
    "q05",
    "q50",
    "q95",
    "workload",
    "configuration",
    "epoch",
)

PREDICTION_WORKLOADS = frozenset(
    {
        "paired_mobilenet",
        "training_median",
        "handcrafted_ridge",
        "paired_resnet50",
        "after_only_mobilenet",
        "frozen_paired_dinov2",
        "fixed_within_category_wrong_pair",
        "observer_score_context_only",
    }
)
CONFIGURED_WORKLOADS = frozenset(
    {
        "paired_mobilenet",
        "paired_resnet50",
        "after_only_mobilenet",
        "fixed_within_category_wrong_pair",
    }
)


@dataclass(frozen=True, slots=True)
class PredictionRecord:
    sample_id: str
    category: str
    outer_fold: int
    target: float
    q05: float
    q50: float
    q95: float
    configuration: str
    epoch: int
    workload: str = "paired_mobilenet"

    def __post_init__(self) -> None:
        values = (self.target, self.q05, self.q50, self.q95)
        if not all(np.isfinite(values)) or not 0 <= self.target <= 1:
            raise ValueError("Prediction values must be finite and target in [0, 1]")
        if not 0 <= self.q05 <= self.q50 <= self.q95 <= 1:
            raise ValueError("Prediction quantiles must be ordered in [0, 1]")
        if self.outer_fold not in range(5) or self.workload not in PREDICTION_WORKLOADS:
            raise ValueError("Prediction fold/workload is invalid")
        if self.workload in CONFIGURED_WORKLOADS:
            if self.configuration not in {"M1", "M2"}:
                raise ValueError("Configured prediction workload requires M1 or M2")
        elif self.configuration:
            raise ValueError("Non-neural reference predictions must not claim M1 or M2")
        if self.epoch < 0:
            raise ValueError("Prediction epoch must be non-negative")

    def to_row(self) -> dict[str, str]:
        return {
            "sample_id": self.sample_id,
            "category": self.category,
            "outer_fold": str(self.outer_fold),
            "target": format(self.target, ".17g"),
            "q05": format(self.q05, ".17g"),
            "q50": format(self.q50, ".17g"),
            "q95": format(self.q95, ".17g"),
            "workload": self.workload,
            "configuration": self.configuration,
            "epoch": str(self.epoch),
        }


def write_predictions(records: list[PredictionRecord], path: str | Path) -> None:
    if len({record.sample_id for record in records}) != len(records):
        raise ValueError("Each frozen prediction must have a unique sample_id")
    prediction_path = Path(path)
    prediction_path.parent.mkdir(parents=True, exist_ok=True)
    with prediction_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTION_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(record.to_row() for record in sorted(records, key=lambda value: value.sample_id))


def read_predictions(path: str | Path) -> list[PredictionRecord]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != PREDICTION_FIELDS:
            raise ValueError("Frozen prediction columns differ from schema")
        records = [
            PredictionRecord(
                sample_id=row["sample_id"],
                category=row["category"],
                outer_fold=int(row["outer_fold"]),
                target=float(row["target"]),
                q05=float(row["q05"]),
                q50=float(row["q50"]),
                q95=float(row["q95"]),
                workload=row["workload"],
                configuration=row["configuration"],
                epoch=int(row["epoch"]),
            )
            for row in reader
        ]
    if len({record.sample_id for record in records}) != len(records):
        raise ValueError("Frozen prediction sample_id values are not unique")
    return records


def validate_prediction_coverage(
    records: list[PredictionRecord], manifest_records: list[ManifestRecord]
) -> None:
    """Bind frozen predictions to every valid manifest row exactly once.

    This prevents an apparently well-formed prediction file from silently
    omitting hard examples or changing targets, categories, or fold labels.
    """

    expected = {record.sample_id: record for record in manifest_records if record.is_valid}
    observed = {record.sample_id: record for record in records}
    if len(observed) != len(records):
        raise ValueError("Frozen prediction sample_id values are not unique")
    missing = sorted(set(expected).difference(observed))
    unexpected = sorted(set(observed).difference(expected))
    if missing or unexpected:
        raise ValueError(
            f"Frozen predictions do not match the valid manifest: "
            f"missing={missing[:5]!r}, unexpected={unexpected[:5]!r}"
        )
    for sample_id, prediction in observed.items():
        source = expected[sample_id]
        if prediction.category != source.category or prediction.outer_fold != source.outer_fold:
            raise ValueError(f"Category/fold mismatch for {sample_id}")
        if not np.isclose(prediction.target, source.leftover_fraction, rtol=0.0, atol=1e-12):
            raise ValueError(f"Target mismatch for {sample_id}")


def evaluate_predictions(
    records: list[PredictionRecord], manifest_records: list[ManifestRecord] | None = None
) -> dict[str, Any]:
    if not records:
        raise ValueError("No prediction records supplied")
    if manifest_records is not None:
        validate_prediction_coverage(records, manifest_records)
    targets = np.asarray([record.target for record in records])
    predictions = np.asarray([record.q50 for record in records])
    categories = np.asarray([record.category for record in records])
    lower = np.asarray([record.q05 for record in records])
    upper = np.asarray([record.q95 for record in records])
    absolute = np.abs(targets - predictions)
    worst_indices = np.argsort(-absolute, kind="stable")[:20]
    return {
        "overall": regression_metrics(targets, predictions, categories).to_dict(),
        "target_slices": metrics_by_slice(
            targets, predictions, categories, target_slice_labels(targets)
        ),
        "interval_gate": evaluate_interval_gate(targets, lower, upper).to_dict(),
        "twenty_largest_errors": [
            {**asdict(records[index]), "absolute_error": float(absolute[index])}
            for index in worst_indices
        ],
    }


def numeric_demo_gate(evaluation: dict[str, Any]) -> bool:
    overall = evaluation["overall"]
    slices = evaluation["target_slices"]
    return bool(
        overall["macro_category_mae"] <= 0.10
        and overall["p90_absolute_error"] <= 0.25
        and all(summary["micro_mae"] <= 0.15 for summary in slices.values())
    )
