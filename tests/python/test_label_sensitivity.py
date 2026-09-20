from __future__ import annotations

import csv
from pathlib import Path

import pytest

from plategauge.errors import DataIntegrityError
from plategauge.label_sensitivity import EXPECTED_PAIRS, build_label_sensitivity_report


def _write_predictions(root: Path, workload: str) -> None:
    fieldnames = (
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
    for fold in range(5):
        path = (
            root
            / "tasks"
            / f"outer.fold-{fold}.{workload}"
            / "workload"
            / "predictions.csv"
        )
        path.parent.mkdir(parents=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for index in range(fold, EXPECTED_PAIRS, 5):
                target = (index % 11) / 10
                offset = 0.2 if workload == "paired_mobilenet" else 0.1
                writer.writerow(
                    {
                        "sample_id": f"sample-{index:04d}",
                        "category": f"{index % 34:03d}",
                        "outer_fold": fold,
                        "target": target,
                        "q05": max(0.0, target - offset),
                        "q50": min(1.0, target + offset),
                        "q95": min(1.0, target + offset + 0.1),
                        "workload": workload,
                        "configuration": "M1",
                        "epoch": 1,
                    }
                )


def test_report_is_explicitly_exploratory_and_immutable(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write_predictions(run, "paired_mobilenet")
    _write_predictions(run, "after_only_mobilenet")
    output = tmp_path / "report.json"
    report = build_label_sensitivity_report(
        run_directory=run,
        excluded_sample_ids=("sample-0001", "sample-0002"),
        output_path=output,
    )
    assert report["confirmatory"] is False
    assert report["changes_frozen_results"] is False
    assert report["retained_count"] == EXPECTED_PAIRS - 2
    assert report["conclusion"]["paired_still_worse_than_after_only"] is True
    assert report["conclusion"]["direction_reversed"] is False
    assert build_label_sensitivity_report(
        run_directory=run,
        excluded_sample_ids=("sample-0002", "sample-0001"),
        output_path=output,
    ) == report


def test_unknown_exclusion_fails_closed(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write_predictions(run, "paired_mobilenet")
    _write_predictions(run, "after_only_mobilenet")
    with pytest.raises(DataIntegrityError, match="Unknown declared"):
        build_label_sensitivity_report(
            run_directory=run,
            excluded_sample_ids=("missing",),
            output_path=tmp_path / "report.json",
        )
