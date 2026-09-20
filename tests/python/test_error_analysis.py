from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from plategauge.data import sha256_file
from plategauge.error_analysis import (
    MANUAL_REVIEW_PENDING,
    PREDEFINED_FAILURE_THEMES,
    build_error_analysis_report,
)
from plategauge.errors import DataIntegrityError
from plategauge.evaluation import PredictionRecord, write_predictions
from plategauge.folds import EXPECTED_FOLD_COUNTS, EXPECTED_VALID_COUNTS, fold_for_category
from plategauge.metrics import regression_metrics
from plategauge.orchestration import (
    PRIMARY_WORKLOAD,
    ExperimentTask,
    FrozenProtocol,
    ProtocolPreflight,
)
from plategauge.post_evaluation import _canonical_sha256
from plategauge.schema import ManifestRecord, write_manifest


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(root: Path) -> tuple[Path, list[ManifestRecord]]:
    records: list[ManifestRecord] = []
    row = 2
    for category, count in EXPECTED_VALID_COUNTS.items():
        for _ in range(count):
            sample_id = f"sample-{row:04d}"
            records.append(
                ManifestRecord(
                    sample_id=sample_id,
                    source_row=row,
                    food_name=f"food-{category}",
                    category=category,
                    before_path=f"{category}/{sample_id}-before.jpg",
                    after_path=f"{category}/{sample_id}-after.jpg",
                    before_mass_g=100.0,
                    after_mass_g=50.0,
                    leftover_fraction=0.5,
                    observer_score=row % 7 + 1,
                    before_width=224,
                    before_height=224,
                    after_width=224,
                    after_height=224,
                    before_sha256=_digest(f"before-{sample_id}"),
                    after_sha256=_digest(f"after-{sample_id}"),
                    outer_fold=fold_for_category(category),
                )
            )
            row += 1
    path = root / "manifest.csv"
    write_manifest(records, path)
    return path, records


def _tasks() -> tuple[ExperimentTask, ...]:
    return tuple(
        ExperimentTask(
            task_id=f"outer.fold-{fold}.{PRIMARY_WORKLOAD}",
            stage="outer",
            workload=PRIMARY_WORKLOAD,
            outer_fold=fold,
            training_folds=tuple(value for value in range(5) if value != fold),
            validation_folds=(),
            evaluation_fold=fold,
            parameters={
                "seed": 20260919,
                "outer_open_policy": "open_once_after_inner_selection",
                "configuration": "M1",
                "epoch": 1,
                "uncertainty_policy": {
                    "interval_correction": 0.0,
                    "abstention_threshold": 0.30,
                },
            },
            expected_counts={
                "training_count": 514 - EXPECTED_FOLD_COUNTS[fold],
                "prediction_count": EXPECTED_FOLD_COUNTS[fold],
            },
            required_artifact_roles=("predictions",),
        )
        for fold in range(5)
    )


def _build_run(
    root: Path,
) -> tuple[Path, Path, tuple[ExperimentTask, ...], FrozenProtocol]:
    manifest_path, records = _manifest(root)
    protocol = FrozenProtocol(
        protocol_id="protocol-test",
        confirmatory_seed=20260919,
        ridge_alphas=(0.1,),
        maximum_epochs=1,
        patience=1,
        config={},
        input_paths={"manifest": str(manifest_path)},
        input_hashes={"manifest": sha256_file(manifest_path)},
    )
    run_dir = root / "run"
    run_core = {
        "schema_version": "1.0",
        "protocol": {
            "protocol_id": protocol.protocol_id,
            "input_hashes": {"manifest": sha256_file(manifest_path)},
        },
        "runner_fingerprint": "runner-test",
        "dataset_verification": {
            "manifest_sha256": sha256_file(manifest_path),
            "record_count": len(records),
        },
    }
    _write_json(run_dir / "run.json", run_core | {"run_id": _canonical_sha256(run_core)})
    tasks = _tasks()
    for fold in range(5):
        _write_json(run_dir / "selections" / f"outer-{fold}.json", {"outer_fold": fold})
    for task in tasks:
        task_dir = run_dir / "tasks" / task.task_id
        workload_dir = task_dir / "workload"
        workload_dir.mkdir(parents=True)
        fold_records = sorted(
            (record for record in records if record.outer_fold == task.outer_fold),
            key=lambda value: value.sample_id,
        )
        predictions: list[PredictionRecord] = []
        for source in fold_records:
            position = (source.source_row - 2) / 513
            q50 = float(np.clip(position, 0.0, 1.0))
            predictions.append(
                PredictionRecord(
                    sample_id=source.sample_id,
                    category=source.category,
                    outer_fold=source.outer_fold,
                    target=source.leftover_fraction,
                    q05=max(0.0, q50 - 0.05),
                    q50=q50,
                    q95=min(1.0, q50 + 0.05),
                    workload=PRIMARY_WORKLOAD,
                    configuration="M1",
                    epoch=1,
                )
            )
        prediction_path = workload_dir / "predictions.csv"
        write_predictions(predictions, prediction_path)
        retained = sorted(prediction.sample_id for prediction in predictions)
        payload = {
            **task.expected_counts,
            "macro_category_mae": regression_metrics(
                [prediction.target for prediction in predictions],
                [prediction.q50 for prediction in predictions],
                [prediction.category for prediction in predictions],
            ).macro_category_mae,
            "interval_correction": 0.0,
            "abstention_threshold": 0.30,
            "retained_count": len(retained),
            "retained_sample_ids": retained,
        }
        spec = task.to_dict()
        result = {
            "schema_version": "1.0",
            "status": "complete",
            "task_id": task.task_id,
            "protocol_id": protocol.protocol_id,
            "task_spec_sha256": _canonical_sha256(spec),
            "runner_fingerprint": "runner-test",
            "payload": payload,
            "payload_sha256": _canonical_sha256(payload),
            "artifacts": [
                {
                    "role": "predictions",
                    "path": "workload/predictions.csv",
                    "size_bytes": prediction_path.stat().st_size,
                    "sha256": sha256_file(prediction_path),
                }
            ],
        }
        _write_json(task_dir / "task.json", spec)
        _write_json(task_dir / "result.json", result)
    return run_dir, manifest_path, tasks, protocol


class ErrorAnalysisTests(unittest.TestCase):
    def _derive(self, root: Path) -> tuple[dict[str, object], Path, Path, tuple[ExperimentTask, ...], FrozenProtocol]:
        run_dir, manifest, tasks, protocol = _build_run(root)
        ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
        output = root / "error_analysis.json"
        with (
            patch("plategauge.error_analysis.protocol_preflight", return_value=(ready, protocol)),
            patch("plategauge.error_analysis.build_outer_tasks", return_value=tasks),
        ):
            report = build_error_analysis_report(
                run_directory=run_dir,
                manifest_path=manifest,
                audit_report_path=root / "audit.json",
                config_path=root / "experiment.toml",
                folds_path=root / "folds.json",
                output_path=output,
            )
        return report, output, manifest, tasks, protocol

    def test_derives_ranked_hash_bound_report_and_identical_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report, output, manifest, tasks, protocol = self._derive(root)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["dataset"]["valid_pairs"], 514)
            largest = report["largest_absolute_errors"]["records"]
            smallest = report["smallest_absolute_errors"]["records"]
            self.assertEqual(len(largest), 20)
            self.assertEqual(len(smallest), 20)
            self.assertEqual(
                [row["absolute_error"] for row in largest],
                sorted((row["absolute_error"] for row in largest), reverse=True),
            )
            self.assertEqual(
                [row["absolute_error"] for row in smallest],
                sorted(row["absolute_error"] for row in smallest),
            )
            for row in [*largest, *smallest]:
                review = row["failure_theme_review"]
                self.assertEqual(review["status"], MANUAL_REVIEW_PENDING)
                self.assertEqual(
                    set(review["theme_assessments"]), set(PREDEFINED_FAILURE_THEMES)
                )
                self.assertEqual(
                    set(review["theme_assessments"].values()),
                    {MANUAL_REVIEW_PENDING},
                )
            core = {key: value for key, value in report.items() if key != "evidence_sha256"}
            self.assertEqual(report["evidence_sha256"], _canonical_sha256(core))
            self.assertEqual(
                len(report["source_artifacts"]["paired_mobilenet_outer_tasks"]), 5
            )
            self.assertNotIn("-before.jpg", output.read_text(encoding="utf-8"))

            ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
            with (
                patch(
                    "plategauge.error_analysis.protocol_preflight",
                    return_value=(ready, protocol),
                ),
                patch("plategauge.error_analysis.build_outer_tasks", return_value=tasks),
            ):
                resumed = build_error_analysis_report(
                    run_directory=root / "run",
                    manifest_path=manifest,
                    audit_report_path=root / "audit.json",
                    config_path=root / "experiment.toml",
                    folds_path=root / "folds.json",
                    output_path=output,
                )
            self.assertEqual(resumed, report)

    def test_rejects_tampered_prediction_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, manifest, tasks, protocol = _build_run(root)
            prediction = (
                run_dir
                / "tasks"
                / f"outer.fold-0.{PRIMARY_WORKLOAD}"
                / "workload"
                / "predictions.csv"
            )
            prediction.write_text(prediction.read_text() + "tamper", encoding="utf-8")
            ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
            output = root / "error_analysis.json"
            with (
                patch(
                    "plategauge.error_analysis.protocol_preflight",
                    return_value=(ready, protocol),
                ),
                patch("plategauge.error_analysis.build_outer_tasks", return_value=tasks),
                self.assertRaisesRegex(DataIntegrityError, "hash/size mismatch"),
            ):
                build_error_analysis_report(
                    run_directory=run_dir,
                    manifest_path=manifest,
                    audit_report_path=root / "audit.json",
                    config_path=root / "experiment.toml",
                    folds_path=root / "folds.json",
                    output_path=output,
                )
            self.assertFalse(output.exists())

    def test_requires_exactly_one_primary_task_per_fold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, manifest, tasks, protocol = _build_run(root)
            ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
            with (
                patch(
                    "plategauge.error_analysis.protocol_preflight",
                    return_value=(ready, protocol),
                ),
                patch("plategauge.error_analysis.build_outer_tasks", return_value=tasks[:-1]),
                self.assertRaisesRegex(DataIntegrityError, "exactly one"),
            ):
                build_error_analysis_report(
                    run_directory=run_dir,
                    manifest_path=manifest,
                    audit_report_path=root / "audit.json",
                    config_path=root / "experiment.toml",
                    folds_path=root / "folds.json",
                    output_path=root / "error_analysis.json",
                )

    def test_refuses_to_replace_a_different_existing_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report, output, manifest, tasks, protocol = self._derive(root)
            _write_json(output, report | {"status": "tampered"})
            ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
            with (
                patch(
                    "plategauge.error_analysis.protocol_preflight",
                    return_value=(ready, protocol),
                ),
                patch("plategauge.error_analysis.build_outer_tasks", return_value=tasks),
                self.assertRaisesRegex(DataIntegrityError, "overwrite"),
            ):
                build_error_analysis_report(
                    run_directory=root / "run",
                    manifest_path=manifest,
                    audit_report_path=root / "audit.json",
                    config_path=root / "experiment.toml",
                    folds_path=root / "folds.json",
                    output_path=output,
                )


if __name__ == "__main__":
    unittest.main()
