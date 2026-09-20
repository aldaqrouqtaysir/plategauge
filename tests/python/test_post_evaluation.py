from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.evaluation import PREDICTION_FIELDS, PredictionRecord, write_predictions
from plategauge.folds import EXPECTED_FOLD_COUNTS, EXPECTED_VALID_COUNTS, fold_for_category
from plategauge.metrics import regression_metrics
from plategauge.orchestration import (
    OUTER_WORKLOADS,
    PRIMARY_WORKLOAD,
    ExperimentTask,
    FrozenProtocol,
    ProtocolPreflight,
)
from plategauge.post_evaluation import (
    EfficiencyEvidence,
    _canonical_bytes,
    _canonical_sha256,
    _category_differences,
    _comparison_payload,
    _decisions,
    _expected_configuration,
    _expected_epoch,
    _immutable_json_write,
    _load_outer_task,
    _prediction_artifact,
    _rank_quintiles,
    _read_json_object,
    _RecordedRunner,
    _safe_relative,
    _validate_outer_predictions,
    _validate_run_descriptor,
    build_frozen_reports,
)
from plategauge.schema import ManifestRecord, write_manifest


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(root: Path) -> tuple[Path, list[ManifestRecord]]:
    records: list[ManifestRecord] = []
    row = 2
    target_values = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    for category, count in EXPECTED_VALID_COUNTS.items():
        for offset in range(count):
            target = target_values[(row + offset) % len(target_values)]
            before_mass = float(100 + row % 30)
            after_mass = before_mass * target
            sample_id = f"sample-{row:04d}"
            records.append(
                ManifestRecord(
                    sample_id=sample_id,
                    source_row=row,
                    food_name=f"food-{category}",
                    category=category,
                    before_path=f"{category}/{sample_id}-before.jpg",
                    after_path=f"{category}/{sample_id}-after.jpg",
                    before_mass_g=before_mass,
                    after_mass_g=after_mass,
                    leftover_fraction=after_mass / before_mass,
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


def _parameters(workload: str) -> dict[str, object]:
    values: dict[str, object] = {"seed": 20260919, "outer_open_policy": "open_once"}
    if workload in {
        PRIMARY_WORKLOAD,
        "after_only_mobilenet",
        "fixed_within_category_wrong_pair",
        "paired_resnet50",
    }:
        values |= {"configuration": "M1", "epoch": 1}
    if workload == PRIMARY_WORKLOAD:
        values["uncertainty_policy"] = {
            "interval_correction": 0.0,
            "abstention_threshold": 0.30,
        }
    return values


def _tasks() -> tuple[ExperimentTask, ...]:
    tasks: list[ExperimentTask] = []
    for fold in range(5):
        for workload in OUTER_WORKLOADS:
            roles = (
                ("predictions", "pairing_map")
                if workload == "fixed_within_category_wrong_pair"
                else ("predictions",)
            )
            tasks.append(
                ExperimentTask(
                    task_id=f"outer.fold-{fold}.{workload}",
                    stage="outer",
                    workload=workload,
                    outer_fold=fold,
                    training_folds=tuple(value for value in range(5) if value != fold),
                    validation_folds=(),
                    evaluation_fold=fold,
                    parameters=_parameters(workload),
                    expected_counts={
                        "training_count": 514 - EXPECTED_FOLD_COUNTS[fold],
                        "prediction_count": EXPECTED_FOLD_COUNTS[fold],
                    },
                    required_artifact_roles=roles,
                )
            )
    return tuple(tasks)


def _prediction(workload: str, source: ManifestRecord, index: int) -> PredictionRecord:
    offsets = {
        PRIMARY_WORKLOAD: 0.02,
        "training_median": 0.10,
        "handcrafted_ridge": 0.06,
        "paired_resnet50": 0.04,
        "after_only_mobilenet": 0.08,
        "frozen_paired_dinov2": 0.01,
        "fixed_within_category_wrong_pair": 0.09,
        "observer_score_context_only": 0.12,
    }
    q50 = float(np.clip(source.leftover_fraction + offsets[workload], 0.0, 1.0))
    point = workload in {
        "training_median",
        "handcrafted_ridge",
        "frozen_paired_dinov2",
        "observer_score_context_only",
    }
    if point or workload == PRIMARY_WORKLOAD:
        q05 = q95 = q50
    else:
        q05, q95 = max(0.0, q50 - 0.005), min(1.0, q50 + 0.005)
    configured = workload in {
        PRIMARY_WORKLOAD,
        "paired_resnet50",
        "after_only_mobilenet",
        "fixed_within_category_wrong_pair",
    }
    return PredictionRecord(
        sample_id=source.sample_id,
        category=source.category,
        outer_fold=source.outer_fold,
        target=source.leftover_fraction,
        q05=q05,
        q50=q50,
        q95=q95,
        workload=workload,
        configuration="M1" if configured else "",
        epoch=1 if configured else 0,
    )


def _build_run(root: Path) -> tuple[Path, Path, tuple[ExperimentTask, ...], FrozenProtocol]:
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
    _json(run_dir / "run.json", run_core | {"run_id": _canonical_sha256(run_core)})
    tasks = _tasks()
    for task in tasks:
        task_dir = run_dir / "tasks" / task.task_id
        workload_dir = task_dir / "workload"
        workload_dir.mkdir(parents=True)
        fold_records = sorted(
            (record for record in records if record.outer_fold == task.outer_fold),
            key=lambda value: value.sample_id,
        )
        predictions = [
            _prediction(task.workload, record, index)
            for index, record in enumerate(fold_records)
        ]
        prediction_path = workload_dir / "predictions.csv"
        write_predictions(predictions, prediction_path)
        targets = [record.target for record in predictions]
        medians = [record.q50 for record in predictions]
        categories = [record.category for record in predictions]
        payload: dict[str, object] = {
            **task.expected_counts,
            "macro_category_mae": regression_metrics(
                targets, medians, categories
            ).macro_category_mae,
        }
        artifacts = [
            {
                "role": "predictions",
                "path": "workload/predictions.csv",
                "size_bytes": prediction_path.stat().st_size,
                "sha256": sha256_file(prediction_path),
            }
        ]
        if task.workload == PRIMARY_WORKLOAD:
            retained = sorted(record.sample_id for record in predictions)
            payload |= {
                "interval_correction": 0.0,
                "abstention_threshold": 0.30,
                "retained_count": len(retained),
                "retained_sample_ids": retained,
            }
        if task.workload == "fixed_within_category_wrong_pair":
            pairing = workload_dir / "pairing_map.csv"
            pairing.write_text("synthetic-test-map\n", encoding="utf-8")
            artifacts.append(
                {
                    "role": "pairing_map",
                    "path": "workload/pairing_map.csv",
                    "size_bytes": pairing.stat().st_size,
                    "sha256": sha256_file(pairing),
                }
            )
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
            "artifacts": artifacts,
        }
        _json(task_dir / "task.json", spec)
        _json(task_dir / "result.json", result)
    return run_dir, manifest_path, tasks, protocol


class PostEvaluationTests(unittest.TestCase):
    def _run(self, root: Path) -> tuple[dict[str, object], dict[str, object], Path, Path]:
        run_dir, manifest, tasks, protocol = _build_run(root)
        ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
        results_path = root / "results.json"
        bootstrap_path = root / "bootstrap.json"
        with (
            patch("plategauge.post_evaluation.protocol_preflight", return_value=(ready, protocol)),
            patch("plategauge.post_evaluation.build_outer_tasks", return_value=tasks),
        ):
            results, bootstrap = build_frozen_reports(
                run_directory=run_dir,
                manifest_path=manifest,
                audit_report_path=root / "audit.json",
                config_path=root / "experiment.toml",
                folds_path=root / "folds.json",
                results_path=results_path,
                bootstrap_path=bootstrap_path,
            )
        return results, bootstrap, results_path, bootstrap_path

    def test_builds_complete_frozen_reports_and_identical_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results, bootstrap, results_path, bootstrap_path = self._run(root)
            self.assertTrue(results["frozen"])
            self.assertEqual(results["dataset"]["valid_pairs"], 514)
            self.assertEqual(set(results["workloads"]), set(OUTER_WORKLOADS))
            self.assertEqual(bootstrap["bootstrap_replicates"], 10_000)
            self.assertEqual(
                bootstrap["comparisons"]["best_non_neural"]["comparator"],
                "handcrafted_ridge",
            )
            self.assertIn("confidence_width_quintile", results["workloads"][PRIMARY_WORKLOAD]["slices"])
            self.assertIsNone(results["decisions"]["efficiency"]["passed"])
            self.assertEqual(len(results["provenance"]["outer_artifacts"]), 40)
            self.assertFalse(results["uncertainty"]["interval_gate"]["passed"])
            self.assertEqual(
                results["decisions"]["release_recommendation"],
                "numeric_estimator_candidate",
            )
            self.assertIn(
                "bootstrap_report_canonical_sha256", results["provenance"]
            )
            self.assertEqual(json.loads(results_path.read_text()), results)
            self.assertEqual(json.loads(bootstrap_path.read_text()), bootstrap)
            _immutable_json_write(results_path, results)
            with self.assertRaisesRegex(DataIntegrityError, "overwrite"):
                _immutable_json_write(results_path, results | {"frozen": False})

    def test_rejects_a_tampered_prediction_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, manifest, tasks, protocol = _build_run(root)
            prediction = (
                run_dir
                / "tasks"
                / "outer.fold-0.paired_mobilenet"
                / "workload"
                / "predictions.csv"
            )
            prediction.write_text(prediction.read_text() + "tamper", encoding="utf-8")
            ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
            with (
                patch("plategauge.post_evaluation.protocol_preflight", return_value=(ready, protocol)),
                patch("plategauge.post_evaluation.build_outer_tasks", return_value=tasks),
                self.assertRaisesRegex(DataIntegrityError, "hash/size mismatch"),
            ):
                build_frozen_reports(
                    run_directory=run_dir,
                    manifest_path=manifest,
                    audit_report_path=root / "audit",
                    config_path=root / "config",
                    folds_path=root / "folds",
                    results_path=root / "results",
                    bootstrap_path=root / "bootstrap",
                )

    def test_rejects_duplicate_sample_even_if_inventory_is_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, manifest, tasks, protocol = _build_run(root)
            task_dir = run_dir / "tasks" / "outer.fold-0.training_median"
            prediction = task_dir / "workload" / "predictions.csv"
            with prediction.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[-1]["sample_id"] = rows[0]["sample_id"]
            with prediction.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=PREDICTION_FIELDS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            result_path = task_dir / "result.json"
            result = json.loads(result_path.read_text())
            result["artifacts"][0]["size_bytes"] = prediction.stat().st_size
            result["artifacts"][0]["sha256"] = sha256_file(prediction)
            _json(result_path, result)
            ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
            with (
                patch("plategauge.post_evaluation.protocol_preflight", return_value=(ready, protocol)),
                patch("plategauge.post_evaluation.build_outer_tasks", return_value=tasks),
                self.assertRaisesRegex(ValueError, "not unique"),
            ):
                build_frozen_reports(
                    run_directory=run_dir,
                    manifest_path=manifest,
                    audit_report_path=root / "audit",
                    config_path=root / "config",
                    folds_path=root / "folds",
                    results_path=root / "results",
                    bootstrap_path=root / "bootstrap",
                )

    def test_missing_outer_task_and_blocked_preflight_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, manifest, tasks, protocol = _build_run(root)
            missing = run_dir / "tasks" / tasks[-1].task_id
            missing.rename(run_dir / "tasks" / "not-an-outer-task")
            ready = ProtocolPreflight("ready", (), protocol.protocol_id, protocol.input_hashes)
            with (
                patch("plategauge.post_evaluation.protocol_preflight", return_value=(ready, protocol)),
                patch("plategauge.post_evaluation.build_outer_tasks", return_value=tasks),
                self.assertRaisesRegex(DataIntegrityError, "directories differ"),
            ):
                build_frozen_reports(
                    run_directory=run_dir,
                    manifest_path=manifest,
                    audit_report_path=root / "audit",
                    config_path=root / "config",
                    folds_path=root / "folds",
                    results_path=root / "results",
                    bootstrap_path=root / "bootstrap",
                )

            blocked = ProtocolPreflight("blocked", ("no",), None, {})
            with (
                patch("plategauge.post_evaluation.protocol_preflight", return_value=(blocked, None)),
                self.assertRaisesRegex(DataIntegrityError, "preflight is blocked"),
            ):
                build_frozen_reports(
                    run_directory=run_dir,
                    manifest_path=manifest,
                    audit_report_path=root / "audit",
                    config_path=root / "config",
                    folds_path=root / "folds",
                    results_path=root / "results",
                    bootstrap_path=root / "bootstrap",
                )

    def test_efficiency_evidence_is_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.onnx"
            model.write_bytes(b"model")
            evidence_path = root / "efficiency.json"
            payload = {
                "schema_version": "1.0",
                "model_path": "model.onnx",
                "model_sha256": sha256_file(model),
                "model_size_bytes": model.stat().st_size,
                "maximum_pytorch_onnx_drift": 0.00001,
            }
            _json(evidence_path, payload)
            evidence = EfficiencyEvidence.from_file(evidence_path)
            self.assertEqual(evidence.model_size_bytes, 5)
            model.write_bytes(b"changed")
            with self.assertRaisesRegex(DataIntegrityError, "size/hash"):
                EfficiencyEvidence.from_file(evidence_path)

    def test_efficiency_evidence_accepts_canonical_export_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "plategauge.onnx"
            model.write_bytes(b"model")
            core: dict[str, object] = {
                "schema_version": "1.0",
                "kind": "frozen_final_onnx_export",
                "status": "passed",
                "model_version": "plategauge/test/model",
                "model_identity": {"protocol_id": "1" * 64, "run_id": "2" * 64},
                "dataset_verification": {},
                "onnx": {
                    "filename": model.name,
                    "sha256": sha256_file(model),
                    "model_bytes": model.stat().st_size,
                },
                "parity": {"maximum_absolute_drift": 0.00001, "passed": True},
                "export_metadata": {},
                "implicit_downloads_allowed": False,
            }
            payload = core | {"evidence_sha256": _canonical_sha256(core)}
            evidence_path = root / "plategauge.onnx.evidence.json"
            _json(evidence_path, payload)
            evidence = EfficiencyEvidence.from_file(evidence_path)
            self.assertEqual(evidence.model_path, model.resolve())
            self.assertEqual(evidence.protocol_id, "1" * 64)
            self.assertEqual(evidence.run_id, "2" * 64)

            payload["parity"] = {"maximum_absolute_drift": 0.00002, "passed": True}
            _json(evidence_path, payload)
            with self.assertRaisesRegex(DataIntegrityError, "evidence hash"):
                EfficiencyEvidence.from_file(evidence_path)

    def test_json_path_and_runner_guards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(DataIntegrityError, "regular file"):
                _read_json_object(root / "missing.json")
            list_path = root / "list.json"
            list_path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "root"):
                _read_json_object(list_path)
            nan_path = root / "nan.json"
            nan_path.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "Non-finite"):
                _read_json_object(nan_path)
            with self.assertRaisesRegex(DataIntegrityError, "canonical"):
                _canonical_bytes({"value": float("nan")})
        for value in (None, "", ".", "../escape", str(Path.cwd().anchor)):
            with self.subTest(value=value), self.assertRaises(DataIntegrityError):
                _safe_relative(value)
        runner = _RecordedRunner("fingerprint")
        self.assertEqual(runner.fingerprint, "fingerprint")
        with self.assertRaisesRegex(DataIntegrityError, "read-only"):
            runner.execute(unittest.mock.MagicMock(), Path("unused"))
        with self.assertRaisesRegex(DataIntegrityError, "empty"):
            _RecordedRunner("")

    def test_efficiency_evidence_rejects_malformed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            model.write_bytes(b"x")
            base: dict[str, object] = {
                "schema_version": "1.0",
                "model_path": "model",
                "model_sha256": sha256_file(model),
                "model_size_bytes": 1,
                "maximum_pytorch_onnx_drift": 0.0,
            }
            invalid = (
                ({**base, "schema_version": "2"}, "schema"),
                ({**base, "model_path": ""}, "model_path"),
                ({**base, "model_path": "missing"}, "regular file"),
                ({**base, "model_sha256": "bad"}, "SHA-256"),
                ({**base, "model_size_bytes": True}, "size/hash"),
                ({**base, "maximum_pytorch_onnx_drift": float("nan")}, "parity"),
                ({**base, "maximum_pytorch_onnx_drift": -1}, "parity"),
            )
            for index, (payload, message) in enumerate(invalid):
                path = root / f"invalid-{index}.json"
                if isinstance(payload["maximum_pytorch_onnx_drift"], float) and np.isnan(
                    payload["maximum_pytorch_onnx_drift"]
                ):
                    path.write_text(
                        json.dumps(payload).replace("NaN", "-1"), encoding="utf-8"
                    )
                else:
                    _json(path, payload)
                with self.subTest(index=index), self.assertRaisesRegex(
                    DataIntegrityError, message
                ):
                    EfficiencyEvidence.from_file(path)

    def test_run_descriptor_guards_each_identity_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, records = _manifest(root)
            base_core: dict[str, object] = {
                "schema_version": "1.0",
                "protocol": {
                    "protocol_id": "protocol",
                    "input_hashes": {"manifest": sha256_file(manifest)},
                },
                "runner_fingerprint": "runner",
                "dataset_verification": {
                    "manifest_sha256": sha256_file(manifest),
                    "record_count": len(records),
                },
            }
            cases: tuple[tuple[str, dict[str, object], str], ...] = (
                ("run", base_core | {"run_id": "bad"}, "run_id"),
                (
                    "schema",
                    {**base_core, "schema_version": "2"},
                    "schema_version",
                ),
                (
                    "protocol",
                    {**base_core, "protocol": {"protocol_id": "wrong"}},
                    "protocol identity",
                ),
                (
                    "dataset",
                    {**base_core, "dataset_verification": {}},
                    "dataset verification",
                ),
                (
                    "runner",
                    {**base_core, "runner_fingerprint": 1},
                    "runner_fingerprint",
                ),
            )
            for name, core, message in cases:
                payload = core if name == "run" else core | {"run_id": _canonical_sha256(core)}
                path = root / f"{name}.json"
                _json(path, payload)
                with self.subTest(name=name), self.assertRaisesRegex(
                    DataIntegrityError, message
                ):
                    _validate_run_descriptor(
                        path,
                        protocol_id="protocol",
                        manifest_path=manifest,
                        record_count=len(records),
                    )

    def test_task_prediction_and_artifact_semantic_guards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, manifest_path, tasks, protocol = _build_run(root)
            manifest_records = {
                record.sample_id: record
                for record in __import__(
                    "plategauge.schema", fromlist=["read_manifest"]
                ).read_manifest(manifest_path)
            }
            task = next(value for value in tasks if value.task_id == "outer.fold-0.training_median")
            task_dir = run_dir / "tasks" / task.task_id
            result = json.loads((task_dir / "result.json").read_text())
            prediction_path = task_dir / "workload" / "predictions.csv"
            predictions = tuple(
                __import__("plategauge.evaluation", fromlist=["read_predictions"]).read_predictions(
                    prediction_path
                )
            )
            with self.assertRaisesRegex(DataIntegrityError, "inventory"):
                _prediction_artifact(task_dir, task, {"artifacts": None})
            with self.assertRaisesRegex(DataIntegrityError, "Malformed"):
                _prediction_artifact(task_dir, task, {"artifacts": [{}]})
            with self.assertRaisesRegex(DataIntegrityError, "roles differ"):
                _prediction_artifact(task_dir, task, {"artifacts": []})
            extra = task_dir / "workload" / "extra"
            extra.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "Undeclared"):
                _prediction_artifact(task_dir, task, result)
            extra.unlink()

            no_fold = ExperimentTask(
                task_id=task.task_id,
                stage=task.stage,
                workload=task.workload,
                outer_fold=task.outer_fold,
                training_folds=task.training_folds,
                validation_folds=task.validation_folds,
                evaluation_fold=None,
                parameters=task.parameters,
                expected_counts=task.expected_counts,
                required_artifact_roles=task.required_artifact_roles,
            )
            with self.assertRaisesRegex(DataIntegrityError, "evaluation fold"):
                _validate_outer_predictions(no_fold, result["payload"], predictions, manifest_records)
            with self.assertRaisesRegex(DataIntegrityError, "cover"):
                _validate_outer_predictions(
                    task, result["payload"], predictions[:-1], manifest_records
                )
            with self.assertRaisesRegex(DataIntegrityError, "payload metric"):
                _validate_outer_predictions(
                    task,
                    {**result["payload"], "macro_category_mae": 999.0},
                    predictions,
                    manifest_records,
                )
            bad_task = ExperimentTask(
                task_id=task.task_id,
                stage=task.stage,
                workload=task.workload,
                outer_fold=task.outer_fold,
                training_folds=task.training_folds,
                validation_folds=task.validation_folds,
                evaluation_fold=task.evaluation_fold,
                parameters={"configuration": 1, "epoch": True},
                expected_counts=task.expected_counts,
                required_artifact_roles=task.required_artifact_roles,
            )
            with self.assertRaisesRegex(DataIntegrityError, "configuration"):
                _expected_configuration(bad_task)
            with self.assertRaisesRegex(DataIntegrityError, "epoch"):
                _expected_epoch(bad_task)

            primary = next(value for value in tasks if value.task_id == "outer.fold-0.paired_mobilenet")
            primary_dir = run_dir / "tasks" / primary.task_id
            primary_result = json.loads((primary_dir / "result.json").read_text())
            primary_predictions = tuple(
                __import__("plategauge.evaluation", fromlist=["read_predictions"]).read_predictions(
                    primary_dir / "workload" / "predictions.csv"
                )
            )
            primary_without_policy = ExperimentTask(
                task_id=primary.task_id,
                stage=primary.stage,
                workload=primary.workload,
                outer_fold=primary.outer_fold,
                training_folds=primary.training_folds,
                validation_folds=primary.validation_folds,
                evaluation_fold=primary.evaluation_fold,
                parameters={"configuration": "M1", "epoch": 1},
                expected_counts=primary.expected_counts,
                required_artifact_roles=primary.required_artifact_roles,
            )
            with self.assertRaisesRegex(DataIntegrityError, "uncertainty policy"):
                _validate_outer_predictions(
                    primary_without_policy,
                    primary_result["payload"],
                    primary_predictions,
                    manifest_records,
                )
            with self.assertRaisesRegex(DataIntegrityError, "retained IDs"):
                _validate_outer_predictions(
                    primary,
                    {**primary_result["payload"], "retained_sample_ids": []},
                    primary_predictions,
                    manifest_records,
                )

            with self.assertRaisesRegex(DataIntegrityError, "specification"):
                _load_outer_task(
                    run_dir,
                    ExperimentTask(
                        task_id=task.task_id,
                        stage=task.stage,
                        workload=task.workload,
                        outer_fold=task.outer_fold,
                        training_folds=task.training_folds,
                        validation_folds=task.validation_folds,
                        evaluation_fold=task.evaluation_fold,
                        parameters=task.parameters | {"extra": True},
                        expected_counts=task.expected_counts,
                        required_artifact_roles=task.required_artifact_roles,
                    ),
                    protocol_id=protocol.protocol_id,
                    runner_fingerprint="runner-test",
                    manifest_by_id=manifest_records,
                )

    def test_comparison_guards_zero_error_and_mismatched_ids(self) -> None:
        first = PredictionRecord("a", "000", 4, 0.0, 0.0, 0.0, 0.0, "", 0, "training_median")
        second = PredictionRecord("b", "000", 4, 0.0, 0.0, 0.0, 0.0, "", 0, "training_median")
        with self.assertRaisesRegex(DataIntegrityError, "identical"):
            _category_differences([first], [second])
        comparison = _comparison_payload([first], [first], comparator_name="zero")
        self.assertIsNone(comparison["relative_improvement"])

    def test_decision_precedence_and_complete_efficiency_gate(self) -> None:
        workloads: dict[str, dict[str, object]] = {}
        for workload, mae in {
            PRIMARY_WORKLOAD: 0.08,
            "training_median": 0.12,
            "handcrafted_ridge": 0.11,
            "frozen_paired_dinov2": 0.07,
        }.items():
            workloads[workload] = {
                "overall": {"macro_category_mae": mae, "p90_absolute_error": 0.20},
                "slices": {"target_range": {"all": {"micro_mae": 0.09}}},
            }
        comparisons = {
            "after_only": {
                "relative_improvement": 0.10,
                "bootstrap": {"upper_95": -0.01},
            },
            "best_non_neural": {
                "relative_improvement": 0.20,
                "bootstrap": {"upper_95": -0.01},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            model.write_bytes(b"ok")
            evidence_path = root / "evidence.json"
            _json(
                evidence_path,
                {
                    "schema_version": "1.0",
                    "model_path": "model",
                    "model_sha256": sha256_file(model),
                    "model_size_bytes": 2,
                    "maximum_pytorch_onnx_drift": 1e-5,
                },
            )
            decisions = _decisions(
                workloads,
                comparisons,
                efficiency_evidence=EfficiencyEvidence.from_file(evidence_path),
            )
        self.assertEqual(decisions["release_recommendation"], "numeric_estimator_candidate")
        self.assertTrue(decisions["efficiency"]["passed"])
        workloads[PRIMARY_WORKLOAD]["overall"]["macro_category_mae"] = 0.21
        stopped = _decisions(
            workloads,
            comparisons,
            efficiency_evidence=None,
        )
        self.assertEqual(stopped["release_recommendation"], "project_stop")

    def test_quintile_input_validation(self) -> None:
        labels = _rank_quintiles(np.arange(10.0), [str(value) for value in range(10)])
        self.assertEqual(set(labels), {"Q1", "Q2", "Q3", "Q4", "Q5"})
        with self.assertRaisesRegex(DataIntegrityError, "at least five"):
            _rank_quintiles(np.arange(4.0), ["a", "b", "c", "d"])


if __name__ == "__main__":
    unittest.main()
