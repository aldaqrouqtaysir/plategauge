from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import numpy as np

from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.folds import EXPECTED_FOLD_COUNTS, FROZEN_CATEGORY_FOLDS
from plategauge.metrics import macro_category_mae
from plategauge.orchestration import (
    CommandTaskRunner,
    ExperimentTask,
    TaskRequest,
    WorkloadResult,
    _expected_final_choice,
    build_final_task,
    build_inner_tasks,
    build_outer_tasks,
    describe_worker_command,
    execute_experiment,
    parse_worker_command,
    protocol_preflight,
    verify_dataset_root,
)
from plategauge.schema import ManifestRecord, read_manifest, write_manifest
from plategauge.workloads import (
    _write_oof_rows,
    _write_pairing_map,
    _write_predictions,
    _wrong_pair_records,
)


def _write_config(path: Path, *, status: str = "approved_for_execution") -> None:
    source = Path(__file__).parents[2] / "configs" / "experiment.toml"
    text = source.read_text(encoding="utf-8").replace(
        'protocol_status = "approved_for_execution"', f'protocol_status = "{status}"'
    )
    path.write_text(text, encoding="utf-8")


def _write_folds(path: Path, *, status: str = "frozen and duplicate-review resolved") -> None:
    payload = {
        "schema_version": "1.0",
        "status": status,
        "folds": {
            str(fold): {
                "categories": list(categories),
                "expected_n": EXPECTED_FOLD_COUNTS[fold],
            }
            for fold, categories in FROZEN_CATEGORY_FOLDS.items()
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_audit(path: Path, manifest: Path, **overrides: Any) -> None:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "passed": True,
        "issues": [],
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
        "fold_counts": {str(key): value for key, value in EXPECTED_FOLD_COUNTS.items()},
        "manifest_sha256": sha256_file(manifest),
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


class SyntheticRunner:
    fingerprint = "synthetic-runner-v1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, request: TaskRequest, workspace: Path) -> WorkloadResult:
        task = request.task
        self.calls.append(task.task_id)
        records = read_manifest(request.manifest_path)
        payload: dict[str, Any] = dict(task.expected_counts)
        if task.stage == "inner_primary":
            configuration = str(task.parameters["configuration"])
            validation_fold = task.validation_folds[0]
            validation = sorted(
                (
                    record
                    for record in records
                    if record.is_valid and record.outer_fold == validation_fold
                ),
                key=lambda record: record.sample_id,
            )
            targets = np.asarray([record.leftover_fraction for record in validation])
            medians = np.clip(targets + (0.0 if configuration == "M1" else 0.2), 0.0, 1.0)
            quantiles = np.repeat(medians[:, None], 3, axis=1)
            best_epoch = 10 + validation_fold
            _write_predictions(
                workspace / "validation_predictions.csv",
                validation,
                quantiles,
                workload=task.workload,
                configuration=configuration,
                epoch=best_epoch,
            )
            (workspace / "checkpoint.json").write_text(
                json.dumps({"task_id": task.task_id}), encoding="utf-8"
            )
            payload |= {
                "best_epoch": best_epoch,
                "macro_category_mae": macro_category_mae(
                    targets,
                    medians,
                    np.asarray([record.category for record in validation]),
                ),
            }
            return WorkloadResult(
                payload=payload,
                artifacts={
                    "checkpoint": "checkpoint.json",
                    "validation_predictions": "validation_predictions.csv",
                },
            )
        if task.stage == "inner_tuning":
            development = sorted(
                (
                    record
                    for record in records
                    if record.is_valid and record.outer_fold in task.training_folds
                ),
                key=lambda record: record.sample_id,
            )
            payload["fold_scores"] = {
                format(float(alpha), "g"): {str(fold): 0.0 for fold in task.validation_folds}
                for alpha in task.parameters["alphas"]
            }
            rows = [
                {
                    "alpha": format(float(alpha), "g"),
                    "validation_fold": fold,
                    "sample_id": record.sample_id,
                    "target": record.leftover_fraction,
                    "prediction": record.leftover_fraction,
                }
                for alpha in task.parameters["alphas"]
                for fold in task.validation_folds
                for record in development
                if record.outer_fold == fold
            ]
            _write_oof_rows(workspace / "oof_predictions.csv", rows)
            return WorkloadResult(
                payload=payload, artifacts={"oof_predictions": "oof_predictions.csv"}
            )
        if task.stage == "outer":
            evaluation = sorted(
                (
                    record
                    for record in records
                    if record.is_valid and record.outer_fold == task.evaluation_fold
                ),
                key=lambda record: record.sample_id,
            )
            targets = np.asarray([record.leftover_fraction for record in evaluation])
            _write_predictions(
                workspace / "predictions.csv",
                evaluation,
                np.repeat(targets[:, None], 3, axis=1),
                workload=task.workload,
                configuration=str(task.parameters.get("configuration", "")),
                epoch=int(task.parameters.get("epoch", 0)),
            )
            payload["macro_category_mae"] = 0.0
            if "uncertainty_policy" in task.parameters:
                policy = task.parameters["uncertainty_policy"]
                payload |= {
                    "interval_correction": float(policy["interval_correction"]),
                    "abstention_threshold": float(policy["abstention_threshold"]),
                    "retained_count": len(evaluation),
                    "retained_sample_ids": [record.sample_id for record in evaluation],
                }
            artifacts = {"predictions": "predictions.csv"}
            if task.workload == "fixed_within_category_wrong_pair":
                training = sorted(
                    (
                        record
                        for record in records
                        if record.is_valid and record.outer_fold in task.training_folds
                    ),
                    key=lambda record: record.sample_id,
                )
                _, training_rows, training_fallback = _wrong_pair_records(
                    training, scope="training"
                )
                _, evaluation_rows, evaluation_fallback = _wrong_pair_records(
                    evaluation, scope="evaluation"
                )
                fallback_ids = sorted((*training_fallback, *evaluation_fallback))
                _write_pairing_map(
                    workspace / "pairing_map.csv", [*training_rows, *evaluation_rows]
                )
                artifacts["pairing_map"] = "pairing_map.csv"
                payload |= {
                    "singleton_fallback_count": len(fallback_ids),
                    "singleton_fallback_sample_ids": fallback_ids,
                }
            return WorkloadResult(payload=payload, artifacts=artifacts)
        (workspace / "model_checkpoint.json").write_text(
            json.dumps({"task_id": task.task_id}), encoding="utf-8"
        )
        return WorkloadResult(
            payload=payload, artifacts={"model_checkpoint": "model_checkpoint.json"}
        )


class OrchestrationTests(unittest.TestCase):
    def make_protocol_files(self, directory: str) -> dict[str, Path]:
        root = Path(directory)
        manifest = root / "manifest.csv"
        records: list[ManifestRecord] = []
        index = 0
        for fold, expected in EXPECTED_FOLD_COUNTS.items():
            category = FROZEN_CATEGORY_FOLDS[fold][0]
            for _ in range(expected):
                target = (index % 11) / 10.0 if index % 11 < 10 else 1.0
                records.append(
                    ManifestRecord(
                        sample_id=f"sample-{index:04d}",
                        source_row=index + 2,
                        food_name="synthetic",
                        category=category,
                        before_path=f"images/before-{index}.png",
                        after_path=f"images/after-{index}.png",
                        before_mass_g=100.0,
                        after_mass_g=target * 100.0,
                        leftover_fraction=target,
                        observer_score=index % 7 + 1,
                        before_width=224,
                        before_height=224,
                        after_width=224,
                        after_height=224,
                        before_sha256=f"{index + 1:064x}",
                        after_sha256=f"{index + 1001:064x}",
                        outer_fold=fold,
                    )
                )
                index += 1
        write_manifest(records, manifest)
        config = root / "experiment.toml"
        folds = root / "folds.json"
        audit = root / "audit.json"
        _write_config(config)
        _write_folds(folds)
        _write_audit(audit, manifest)
        dataset = root / "dataset"
        dataset.mkdir()
        return {
            "manifest": manifest,
            "config": config,
            "folds": folds,
            "audit": audit,
            "dataset": dataset,
            "output": root / "run",
        }

    def execute(self, paths: dict[str, Path], runner: SyntheticRunner, stage: str):
        verification = {
            "schema_version": "1.0",
            "manifest_sha256": sha256_file(paths["manifest"]),
            "record_count": 514,
            "unique_image_count": 1028,
            "image_inventory_sha256": "f" * 64,
        }
        with mock.patch("plategauge.orchestration.verify_dataset_root", return_value=verification):
            return execute_experiment(
                audit_report_path=paths["audit"],
                manifest_path=paths["manifest"],
                dataset_root=paths["dataset"],
                output_directory=paths["output"],
                runner=runner,
                stage=stage,
                config_path=paths["config"],
                folds_path=paths["folds"],
            )

    def test_preflight_fingerprints_exact_approved_inputs_and_builds_frozen_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            preflight, protocol = protocol_preflight(
                audit_report_path=paths["audit"],
                manifest_path=paths["manifest"],
                config_path=paths["config"],
                folds_path=paths["folds"],
            )
            self.assertEqual(preflight.status, "ready")
            self.assertIsNotNone(protocol)
            assert protocol is not None
            tasks = build_inner_tasks(protocol)
        self.assertEqual(len(tasks), 50)
        self.assertEqual(sum(task.stage == "inner_primary" for task in tasks), 40)
        self.assertEqual(sum(task.stage == "inner_tuning" for task in tasks), 10)
        primary = tasks[0]
        self.assertNotIn(primary.outer_fold, primary.training_folds)
        self.assertNotIn(primary.outer_fold, primary.validation_folds)
        dino = next(task for task in tasks if task.workload == "frozen_paired_dinov2")
        self.assertEqual(dino.parameters["input_size"], 518)
        self.assertTrue(dino.parameters["cache_embeddings"])

    def test_all_stages_freeze_inner_selection_before_outer_and_resume_immutably(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            runner = SyntheticRunner()
            summary = self.execute(paths, runner, "all")
            self.assertEqual(summary.executed_tasks, 91)
            self.assertEqual(summary.selections_written, 6)
            self.assertEqual(len(runner.calls), 91)
            final_choice = json.loads(
                (paths["output"] / "selections" / "final.json").read_text(encoding="utf-8")
            )
            self.assertEqual(final_choice["configuration"], "M1")
            self.assertEqual(final_choice["epoch"], 12)
            self.assertEqual(
                final_choice["information_boundary"], "inner_selections_only_no_outer_metrics"
            )
            final_policy = final_choice["uncertainty_policy"]
            self.assertEqual(
                [entry["outer_fold"] for entry in final_policy["included_outer_selections"]],
                [0, 1, 2, 3, 4],
            )
            self.assertEqual(final_policy["excluded_outer_selections"], [])

            _, protocol = protocol_preflight(
                audit_report_path=paths["audit"],
                manifest_path=paths["manifest"],
                config_path=paths["config"],
                folds_path=paths["folds"],
            )
            assert protocol is not None
            outer_tasks = build_outer_tasks(protocol, paths["output"], runner)
            after_only = next(
                task
                for task in outer_tasks
                if task.outer_fold == 0 and task.workload == "after_only_mobilenet"
            )
            wrong_pair = next(
                task
                for task in outer_tasks
                if task.outer_fold == 0 and task.workload == "fixed_within_category_wrong_pair"
            )
            resnet = next(
                task
                for task in outer_tasks
                if task.outer_fold == 0 and task.workload == "paired_resnet50"
            )
            self.assertEqual(after_only.parameters["configuration"], "M1")
            self.assertEqual(wrong_pair.parameters["epoch"], after_only.parameters["epoch"])
            self.assertEqual(resnet.parameters["configuration"], "M1")
            self.assertEqual(resnet.parameters["input_size"], 224)

            resumed = self.execute(paths, runner, "all")
            self.assertEqual(resumed.executed_tasks, 0)
            self.assertEqual(resumed.resumed_tasks, 91)
            self.assertEqual(resumed.selections_written, 0)
            self.assertEqual(len(runner.calls), 91)

    def test_outer_cannot_open_before_all_inner_results_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            with self.assertRaises((DataIntegrityError, FileNotFoundError)):
                self.execute(paths, SyntheticRunner(), "outer")

    def test_corrupt_artifact_and_changed_protocol_are_rejected_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            runner = SyntheticRunner()
            self.execute(paths, runner, "inner")
            artifact = next((paths["output"] / "tasks").rglob("checkpoint.json"))
            artifact.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "hash/size mismatch"):
                self.execute(paths, runner, "inner")

        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            runner = SyntheticRunner()
            self.execute(paths, runner, "inner")
            _write_config(paths["config"], status="approved_for_execution")
            with paths["config"].open("a", encoding="utf-8") as handle:
                handle.write("# identity-changing but valid comment\n")
            with self.assertRaisesRegex(DataIntegrityError, "Run identity differs"):
                self.execute(paths, runner, "inner")

    def test_preflight_blocks_unbound_manifest_and_unresolved_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            _write_audit(paths["audit"], paths["manifest"], manifest_sha256="0" * 64)
            _write_config(paths["config"], status="blocked_at_data_gate")
            _write_folds(paths["folds"], status="preregistered; unresolved")
            preflight, protocol = protocol_preflight(
                audit_report_path=paths["audit"],
                manifest_path=paths["manifest"],
                config_path=paths["config"],
                folds_path=paths["folds"],
            )
        self.assertEqual(preflight.status, "blocked")
        self.assertIsNone(protocol)
        self.assertIn("manifest_sha256", preflight.blocker or "")
        self.assertIn("protocol_status", preflight.blocker or "")
        self.assertIn("folds status", preflight.blocker or "")

    def test_preflight_rejects_each_locked_config_class(self) -> None:
        mutations = (
            ("maximum_total_gpu_hours = 10", "maximum_total_gpu_hours = 11", "gpu_hours"),
            ("batch_size = 32", "batch_size = 1", "batch_size"),
            ("resize_shorter_edge = 256", "resize_shorter_edge = 255", "preprocessing"),
            ("vertical_flip = false", "vertical_flip = true", "augmentation"),
            ("interval_loss_weight = 0.5", "interval_loss_weight = 0.9", "model"),
            (
                "maximum_abstention_width = 0.30",
                "maximum_abstention_width = 0.99",
                "uncertainty",
            ),
        )
        for original, replacement, expected_path in mutations:
            with (
                self.subTest(expected_path=expected_path),
                tempfile.TemporaryDirectory() as directory,
            ):
                paths = self.make_protocol_files(directory)
                text = paths["config"].read_text(encoding="utf-8")
                self.assertIn(original, text)
                paths["config"].write_text(text.replace(original, replacement), encoding="utf-8")
                preflight, protocol = protocol_preflight(
                    audit_report_path=paths["audit"],
                    manifest_path=paths["manifest"],
                    config_path=paths["config"],
                    folds_path=paths["folds"],
                )
                self.assertEqual(preflight.status, "blocked")
                self.assertIsNone(protocol)
                self.assertIn(expected_path, preflight.blocker or "")

    def test_selection_and_uncertainty_policy_are_recomputed_before_outer_or_final(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            runner = SyntheticRunner()
            self.execute(paths, runner, "inner")
            self.execute(paths, runner, "select")
            _, protocol = protocol_preflight(
                audit_report_path=paths["audit"],
                manifest_path=paths["manifest"],
                config_path=paths["config"],
                folds_path=paths["folds"],
            )
            assert protocol is not None
            outer_path = paths["output"] / "selections" / "outer-0.json"
            original_outer = outer_path.read_text(encoding="utf-8")
            outer = json.loads(original_outer)
            policy = outer["uncertainty_policy"]
            self.assertEqual(len(policy["sources"]), 4)
            self.assertEqual(policy["calibration_count"], 411)
            self.assertEqual(policy["method"], "selected_primary_inner_validation_predictions_only")

            outer["uncertainty_policy"]["abstention_threshold"] = 0.99
            outer_path.write_text(json.dumps(outer), encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "tampered"):
                build_outer_tasks(protocol, paths["output"], runner)
            outer_path.write_text(original_outer, encoding="utf-8")

            final_path = paths["output"] / "selections" / "final.json"
            original_final = final_path.read_text(encoding="utf-8")
            final = json.loads(original_final)
            final["uncertainty_policy"]["included_outer_selections"][0]["outer_fold"] = 4
            final_path.write_text(json.dumps(final), encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "stale or test-informed"):
                build_final_task(protocol, paths["output"], runner)

            final_path.write_text(original_final, encoding="utf-8")
            final = json.loads(original_final)
            final["configuration"] = "M2"
            final_path.write_text(json.dumps(final), encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "stale or test-informed"):
                build_final_task(protocol, paths["output"], runner)

    def test_final_uncertainty_policy_uses_only_modal_configuration_policies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            selections_directory = output / "selections"
            selections_directory.mkdir()
            configurations = ("M1", "M2", "M1", "M2", "M1")
            epochs = (10, 60, 20, 70, 30)
            corrections = (0.10, 0.80, 0.30, 0.90, 0.50)
            thresholds = (0.11, 0.81, 0.13, 0.91, 0.15)
            payloads: list[dict[str, Any]] = []
            for fold, configuration, epoch, correction, threshold in zip(
                sorted(FROZEN_CATEGORY_FOLDS),
                configurations,
                epochs,
                corrections,
                thresholds,
                strict=True,
            ):
                payloads.append(
                    {
                        "primary": {
                            "configuration": configuration,
                            "epoch": epoch,
                            "mean_inner_macro_category_mae": 0.1,
                        },
                        "uncertainty_policy": {
                            "interval_correction": correction,
                            "abstention_threshold": threshold,
                        },
                    }
                )
                (selections_directory / f"outer-{fold}.json").write_text(
                    json.dumps({"outer_fold": fold}), encoding="utf-8"
                )

            with mock.patch("plategauge.orchestration._read_selection", side_effect=payloads):
                final = _expected_final_choice(
                    output,
                    SimpleNamespace(protocol_id="protocol-for-policy-test"),
                    SyntheticRunner(),
                )

        self.assertEqual(final["configuration"], "M1")
        # The epoch rule remains the median across all five selections, not just M1.
        self.assertEqual(final["epoch"], 30)
        policy = final["uncertainty_policy"]
        self.assertEqual(
            policy["method"],
            "median_of_inner_only_outer_policies_matching_final_configuration",
        )
        self.assertEqual(policy["interval_correction"], 0.30)
        self.assertEqual(policy["abstention_threshold"], 0.13)
        self.assertEqual(
            [entry["outer_fold"] for entry in policy["included_outer_selections"]],
            [0, 2, 4],
        )
        self.assertTrue(
            all(
                entry["selected_primary_configuration"] == "M1"
                for entry in policy["included_outer_selections"]
            )
        )
        self.assertEqual(
            policy["excluded_outer_selections"],
            [
                {"outer_fold": 1, "selected_primary_configuration": "M2"},
                {"outer_fold": 3, "selected_primary_configuration": "M2"},
            ],
        )

    def test_semantic_resume_validation_rejects_forged_prediction_and_oof_rows(self) -> None:
        def update_recorded_hash(artifact: Path) -> None:
            result_path = artifact.parent.parent / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            relative = artifact.relative_to(artifact.parent.parent).as_posix()
            entry = next(item for item in result["artifacts"] if item["path"] == relative)
            entry["sha256"] = sha256_file(artifact)
            entry["size_bytes"] = artifact.stat().st_size
            result_path.write_text(json.dumps(result), encoding="utf-8")

        for role, field in (
            ("validation_predictions.csv", "target"),
            ("oof_predictions.csv", "sample_id"),
        ):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                paths = self.make_protocol_files(directory)
                runner = SyntheticRunner()
                self.execute(paths, runner, "inner")
                artifact = next((paths["output"] / "tasks").rglob(role))
                with artifact.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    fieldnames = list(reader.fieldnames or ())
                    rows = list(reader)
                if field == "target":
                    rows[0][field] = "0.123456789"
                else:
                    rows[1][field] = rows[0][field]
                with artifact.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(rows)
                update_recorded_hash(artifact)
                with self.assertRaisesRegex(
                    DataIntegrityError,
                    "metadata differs|duplicate or unexpected",
                ):
                    self.execute(paths, runner, "inner")

    def test_payload_hash_is_recomputed_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            runner = SyntheticRunner()
            self.execute(paths, runner, "inner")
            result_path = next((paths["output"] / "tasks").rglob("result.json"))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["payload_sha256"] = "0" * 64
            result_path.write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "payload hash mismatch"):
                self.execute(paths, runner, "inner")

    def test_runner_result_contract_rejects_bad_counts_and_undeclared_files(self) -> None:
        class BadRunner(SyntheticRunner):
            fingerprint = "bad-runner"

            def execute(self, request: TaskRequest, workspace: Path) -> WorkloadResult:
                result = super().execute(request, workspace)
                if request.task.stage == "inner_primary":
                    result.payload["training_count"] = -1
                return result

        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            with self.assertRaisesRegex(DataIntegrityError, "training_count"):
                self.execute(paths, BadRunner(), "inner")

        class ExtraFileRunner(SyntheticRunner):
            fingerprint = "extra-file-runner"

            def execute(self, request: TaskRequest, workspace: Path) -> WorkloadResult:
                result = super().execute(request, workspace)
                (workspace / "undeclared.txt").write_text("no", encoding="utf-8")
                return result

        with tempfile.TemporaryDirectory() as directory:
            paths = self.make_protocol_files(directory)
            with self.assertRaisesRegex(DataIntegrityError, "Undeclared"):
                self.execute(paths, ExtraFileRunner(), "inner")

    def test_run_start_dataset_verification_binds_every_image_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            image.write_bytes(b"immutable-image")
            manifest = root / "manifest.csv"
            manifest.write_text("manifest", encoding="utf-8")
            digest = sha256_file(image)
            record = SimpleNamespace(
                before_path="image.png",
                before_sha256=digest,
                after_path="image.png",
                after_sha256=digest,
            )
            with mock.patch("plategauge.orchestration.read_manifest", return_value=[record]):
                verified = verify_dataset_root(manifest, root)
                self.assertEqual(verified["record_count"], 1)
                self.assertEqual(verified["unique_image_count"], 1)
                image.write_bytes(b"substituted")
                with self.assertRaisesRegex(DataIntegrityError, "hash mismatch"):
                    verify_dataset_root(manifest, root)

    def test_command_runner_uses_json_contract_without_a_shell(self) -> None:
        task = ExperimentTask(
            task_id="synthetic.command",
            stage="outer",
            workload="training_median",
            outer_fold=0,
            training_folds=(1, 2, 3, 4),
            validation_folds=(),
            evaluation_fold=0,
            parameters={},
            expected_counts={"training_count": 411, "prediction_count": 103},
            required_artifact_roles=("predictions",),
        )
        request = TaskRequest("1.0", "protocol", "manifest.csv", "dataset", task)
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory)
            workspace = control / "workload"
            workspace.mkdir()

            def complete(command: list[str], **_: Any) -> SimpleNamespace:
                self.assertEqual(command[0:2], ["worker executable", "--fixed"])
                (workspace / "predictions.csv").write_text("artifact", encoding="utf-8")
                Path(command[-1]).write_text(
                    json.dumps(
                        {
                            "schema_version": "1.0",
                            "task_id": task.task_id,
                            "payload": task.expected_counts,
                            "artifacts": {"predictions": "predictions.csv"},
                        }
                    ),
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            runner = CommandTaskRunner(("worker executable", "--fixed"))
            with mock.patch("plategauge.orchestration.subprocess.run", side_effect=complete):
                result = runner.execute(request, workspace)
            self.assertEqual(result.artifacts, {"predictions": "predictions.csv"})
            self.assertEqual(
                parse_worker_command("worker executable", ("--fixed",)), runner.command
            )
            self.assertIn("'worker executable'", describe_worker_command(runner.command))

            failure_workspace = control / "failure" / "workload"
            failure_workspace.mkdir(parents=True)
            with (
                mock.patch(
                    "plategauge.orchestration.subprocess.run",
                    return_value=SimpleNamespace(returncode=2, stdout="", stderr="failed"),
                ),
                self.assertRaisesRegex(DataIntegrityError, "exit 2"),
            ):
                runner.execute(request, failure_workspace)
        with self.assertRaisesRegex(ValueError, "non-empty"):
            parse_worker_command(" ", ())
        with self.assertRaisesRegex(ValueError, "at least one"):
            CommandTaskRunner(())


if __name__ == "__main__":
    unittest.main()
