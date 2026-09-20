from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

import numpy as np

from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.folds import fold_for_category
from plategauge.orchestration import ExperimentTask, FrozenProtocol, _canonical_sha256
from plategauge.same_category_diagnostic import (
    DiagnosticContext,
    DiagnosticPrediction,
    _execute_task,
    _initialize_output,
    _load_frozen_assignments,
    _partition,
    _read_predictions,
    _RecordedRunner,
    _require_matching_runner,
    _run_descriptor,
    _source_task_for_fold,
    _strict_json_object,
    _task_spec,
    _validate_completed_task,
    _validate_confirmatory_run,
    _validate_predictions,
    _validated_primary_predictions,
    _write_predictions,
    aggregate_same_category_diagnostic,
    build_summary_payload,
    fit_same_category_diagnostic,
    load_diagnostic_context,
    preflight_same_category_diagnostic,
)
from plategauge.schema import ManifestRecord
from plategauge.workloads import ProductionTaskRunner


def _record(index: int, category: str, fraction: float) -> ManifestRecord:
    return ManifestRecord(
        sample_id=f"sample-{index}",
        source_row=index + 2,
        food_name="synthetic",
        category=category,
        before_path=f"images/before-{index}.png",
        after_path=f"images/after-{index}.png",
        before_mass_g=100.0,
        after_mass_g=100.0 * fraction,
        leftover_fraction=fraction,
        observer_score=4,
        before_width=32,
        before_height=32,
        after_width=32,
        after_height=32,
        before_sha256=f"{index + 1:064x}",
        after_sha256=f"{index + 101:064x}",
        outer_fold=fold_for_category(category),
    )


def _source_task(fold: int) -> ExperimentTask:
    return ExperimentTask(
        task_id=f"outer.fold-{fold}.paired_mobilenet",
        stage="outer",
        workload="paired_mobilenet",
        outer_fold=fold,
        training_folds=tuple(value for value in range(5) if value != fold),
        validation_folds=(),
        evaluation_fold=fold,
        parameters={
            "configuration": "M2",
            "epoch": 3 + fold,
            "seed": 20260919,
            "batch_size": 32,
        },
        expected_counts={"training_count": 3, "prediction_count": 1},
        required_artifact_roles=("predictions",),
    )


def _context(root: Path) -> DiagnosticContext:
    records = (
        _record(0, "001", 0.10),
        _record(1, "001", 0.30),
        _record(2, "002", 0.60),
        _record(3, "003", 0.80),
    )
    assignments = {
        "sample-0": 0,
        "sample-1": 1,
        "sample-2": 0,
        "sample-3": 1,
    }
    selections = root / "selections"
    selections.mkdir(parents=True)
    for fold in range(5):
        (selections / f"outer-{fold}.json").write_text(json.dumps({"fold": fold}), encoding="utf-8")
    (root / "split.json").write_text("{}", encoding="utf-8")
    (root / "report.json").write_text("{}", encoding="utf-8")
    return DiagnosticContext(
        protocol=cast(FrozenProtocol, SimpleNamespace(protocol_id="protocol")),
        confirmatory_run={"run_id": "confirmatory", "runner_fingerprint": "f" * 64},
        records=records,
        assignments=assignments,
        source_tasks=tuple(_source_task(fold) for fold in range(5)),
        dataset_verification={"record_count": 4},
        split_path=root / "split.json",
        split_report_path=root / "report.json",
        confirmatory_directory=root,
    )


def _task(context: DiagnosticContext, fold: int) -> dict[str, Any]:
    return _task_spec(context, fold)


def _predictions(context: DiagnosticContext, task: dict[str, Any]) -> list[DiagnosticPrediction]:
    training, evaluation = _partition(context, int(task["diagnostic_fold"]))
    training_categories = {record.category for record in training}
    return [
        DiagnosticPrediction(
            sample_id=record.sample_id,
            category=record.category,
            diagnostic_fold=int(task["diagnostic_fold"]),
            target=record.leftover_fraction,
            raw_q05=max(0.0, record.leftover_fraction - 0.1),
            raw_q50=record.leftover_fraction,
            raw_q95=min(1.0, record.leftover_fraction + 0.1),
            configuration=str(task["parameters"]["configuration"]),
            epoch=int(task["parameters"]["epoch"]),
            category_seen_in_training=record.category in training_categories,
        )
        for record in evaluation
    ]


class DiagnosticPredictionTests(unittest.TestCase):
    def test_prediction_round_trip_and_invalid_values(self) -> None:
        prediction = DiagnosticPrediction("sample", "001", 2, 0.4, 0.2, 0.4, 0.6, "M1", 5, True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            _write_predictions(path, [prediction])
            self.assertEqual(_read_predictions(path), [prediction])
        with self.assertRaisesRegex(ValueError, "ordered"):
            DiagnosticPrediction("x", "001", 0, 0.4, 0.5, 0.4, 0.6, "M1", 1, True)
        with self.assertRaisesRegex(ValueError, "finite"):
            DiagnosticPrediction("x", "001", 0, 0.4, 0.1, float("nan"), 0.6, "M1", 1, True)
        for changed, message in (
            ({"target": 1.1}, "target"),
            ({"diagnostic_fold": 5}, "fold"),
            ({"configuration": "M3"}, "configuration/epoch"),
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, message):
                replace(prediction, **changed)

    def test_reader_rejects_schema_and_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("sample_id\nx\n", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "columns"):
                _read_predictions(path)

            prediction = DiagnosticPrediction("x", "001", 0, 0.4, 0.2, 0.4, 0.6, "M1", 1, True)
            duplicate = Path(directory) / "duplicate.csv"
            _write_predictions(duplicate, [prediction])
            text = duplicate.read_text(encoding="utf-8")
            duplicate.write_text(text + text.splitlines()[-1] + "\n", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "repeat"):
                _read_predictions(duplicate)

            invalid_boolean = Path(directory) / "invalid-boolean.csv"
            _write_predictions(invalid_boolean, [prediction])
            invalid_boolean.write_text(
                invalid_boolean.read_text(encoding="utf-8").replace(",true\n", ",unknown\n"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DataIntegrityError, "must be 'true' or 'false'"):
                _read_predictions(invalid_boolean)


class FrozenInputTests(unittest.TestCase):
    def test_strict_json_and_recorded_runner_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            malformed = root / "malformed.json"
            malformed.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "Non-finite"):
                _strict_json_object(malformed)
            not_object = root / "list.json"
            not_object.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "root"):
                _strict_json_object(not_object)
        with self.assertRaisesRegex(DataIntegrityError, "empty"):
            _RecordedRunner("")
        recorded = _RecordedRunner("fingerprint")
        self.assertEqual(recorded.fingerprint, "fingerprint")
        with self.assertRaisesRegex(DataIntegrityError, "read-only"):
            recorded.execute(cast(Any, None), Path("unused"))

    def test_confirmatory_descriptor_is_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.csv"
            manifest.write_text("frozen-manifest", encoding="utf-8")
            core = {
                "schema_version": "1.0",
                "protocol": {
                    "protocol_id": "protocol",
                    "input_hashes": {"manifest": sha256_file(manifest)},
                },
                "runner_fingerprint": "f" * 64,
            }
            from plategauge.orchestration import _canonical_sha256

            run = root / "run.json"
            run.write_text(
                json.dumps(core | {"run_id": _canonical_sha256(core)}),
                encoding="utf-8",
            )
            protocol = cast(FrozenProtocol, SimpleNamespace(protocol_id="protocol"))
            self.assertEqual(
                _validate_confirmatory_run(run, protocol, manifest)["run_id"],
                _canonical_sha256(core),
            )
            payload = json.loads(run.read_text(encoding="utf-8"))
            payload["run_id"] = "tampered"
            run.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "run_id"):
                _validate_confirmatory_run(run, protocol, manifest)

            for mutation, message in (
                ({"protocol_id": "other"}, "frozen protocol"),
                ({"input_hashes": {"manifest": "0" * 64}}, "supplied manifest"),
            ):
                changed_core = dict(core)
                changed_core["protocol"] = {**core["protocol"], **mutation}
                run.write_text(
                    json.dumps(changed_core | {"run_id": _canonical_sha256(changed_core)}),
                    encoding="utf-8",
                )
                with (
                    self.subTest(mutation=mutation),
                    self.assertRaisesRegex(DataIntegrityError, message),
                ):
                    _validate_confirmatory_run(run, protocol, manifest)
            bad_fingerprint = {**core, "runner_fingerprint": "short"}
            run.write_text(
                json.dumps(bad_fingerprint | {"run_id": _canonical_sha256(bad_fingerprint)}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DataIntegrityError, "fingerprint"):
                _validate_confirmatory_run(run, protocol, manifest)

    def test_runner_identity_must_match(self) -> None:
        runner = cast(ProductionTaskRunner, SimpleNamespace(fingerprint="a" * 64))
        _require_matching_runner({"runner_fingerprint": "a" * 64}, runner)
        with self.assertRaisesRegex(DataIntegrityError, "exact confirmatory"):
            _require_matching_runner({"runner_fingerprint": "b" * 64}, runner)

    def test_split_and_freeze_report_are_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            split = root / "split.json"
            report = root / "report.json"
            manifest = root / "manifest.csv"
            run = root / "run.json"
            split.write_text(
                json.dumps(
                    {
                        "split_id": "split",
                        "assignments": [{"sample_id": "a", "diagnostic_fold": 0}],
                    }
                ),
                encoding="utf-8",
            )
            report.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "split_id": "split",
                        "config_sha256": sha256_file(split),
                        "frozen_before_outer_results": True,
                        "outer_result_artifact_count_at_freeze": 0,
                        "outer_result_paths_at_freeze": [],
                    }
                ),
                encoding="utf-8",
            )
            manifest.write_text("manifest", encoding="utf-8")
            run.write_text("{}", encoding="utf-8")
            with (
                mock.patch(
                    "plategauge.same_category_diagnostic.FROZEN_SPLIT_SHA256",
                    sha256_file(split),
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic.FROZEN_SPLIT_REPORT_SHA256",
                    sha256_file(report),
                ),
                mock.patch("plategauge.same_category_diagnostic.FROZEN_SPLIT_ID", "split"),
                mock.patch(
                    "plategauge.same_category_diagnostic.validate_split_artifact",
                    return_value={"passed": True},
                ),
            ):
                assignments, _ = _load_frozen_assignments(split, report, manifest, run)
                self.assertEqual(assignments, {"a": 0})
                split.write_text(split.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                with self.assertRaisesRegex(DataIntegrityError, "frozen hash"):
                    _load_frozen_assignments(split, report, manifest, run)
            with (
                mock.patch(
                    "plategauge.same_category_diagnostic.FROZEN_SPLIT_SHA256",
                    sha256_file(split),
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic.FROZEN_SPLIT_REPORT_SHA256",
                    "0" * 64,
                ),
                self.assertRaisesRegex(DataIntegrityError, "freeze report"),
            ):
                _load_frozen_assignments(split, report, manifest, run)

    def test_context_loader_reconstructs_only_inner_selected_recipes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = _context(root).records
            assignments = {
                "sample-0": 0,
                "sample-1": 1,
                "sample-2": 0,
                "sample-3": 1,
            }
            protocol = cast(FrozenProtocol, SimpleNamespace(protocol_id="protocol"))
            preflight = SimpleNamespace(status="ready", blocker=None)
            runner = cast(ProductionTaskRunner, SimpleNamespace(fingerprint="f" * 64))
            source_tasks = tuple(_source_task(fold) for fold in range(5))
            with (
                mock.patch(
                    "plategauge.same_category_diagnostic.protocol_preflight",
                    return_value=(preflight, protocol),
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic._validate_confirmatory_run",
                    return_value={"run_id": "run", "runner_fingerprint": "f" * 64},
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic._load_frozen_assignments",
                    return_value=(assignments, {}),
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic.read_manifest",
                    return_value=list(records),
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic.build_outer_tasks",
                    return_value=source_tasks,
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic.verify_dataset_root",
                    return_value={"record_count": 4},
                ),
                mock.patch("plategauge.same_category_diagnostic.EXPECTED_VALID_ROWS", 4),
                mock.patch("plategauge.same_category_diagnostic.EXPECTED_SEEN_ROWS", 2),
                mock.patch("plategauge.same_category_diagnostic.EXPECTED_SEEN_CATEGORIES", 1),
            ):
                loaded = load_diagnostic_context(
                    runner=runner,
                    manifest_path=root / "manifest.csv",
                    dataset_root=root,
                    confirmatory_directory=root,
                    split_path=root / "split.json",
                    split_report_path=root / "report.json",
                )
            self.assertEqual(len(loaded.source_tasks), 5)
            self.assertEqual(loaded.dataset_verification, {"record_count": 4})

            blocked = SimpleNamespace(status="blocked", blocker="blocked fixture")
            with (
                mock.patch(
                    "plategauge.same_category_diagnostic.protocol_preflight",
                    return_value=(blocked, None),
                ),
                self.assertRaisesRegex(DataIntegrityError, "blocked fixture"),
            ):
                load_diagnostic_context(runner=runner)


class DiagnosticRunContractTests(unittest.TestCase):
    def test_descriptor_preflight_and_output_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root / "confirmatory")
            runner = ProductionTaskRunner(device="cpu")
            descriptor = _run_descriptor(context, runner)
            self.assertEqual(descriptor["kind"], "secondary_same_category_diagnostic")
            self.assertEqual(descriptor["tasks_sha256"], descriptor["tasks_sha256"])
            self.assertEqual(
                descriptor["implementation"]["path"],
                "src/plategauge/same_category_diagnostic.py",
            )
            self.assertFalse(Path(descriptor["implementation"]["path"]).is_absolute())
            output = root / "output"
            _initialize_output(output, descriptor)
            _initialize_output(output, descriptor)
            changed = {**descriptor, "run_id": "different"}
            with self.assertRaisesRegex(DataIntegrityError, "identity changed"):
                _initialize_output(output, changed)
            nonempty = root / "nonempty"
            nonempty.mkdir()
            (nonempty / "orphan").write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "non-empty"):
                _initialize_output(nonempty, descriptor)

            with (
                mock.patch(
                    "plategauge.same_category_diagnostic.load_diagnostic_context",
                    return_value=context,
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic._run_descriptor",
                    return_value=descriptor,
                ),
            ):
                ready = preflight_same_category_diagnostic(runner=runner)
            self.assertFalse(ready["outer_results_read"])
            with self.assertRaisesRegex(TypeError, "ProductionTaskRunner"):
                preflight_same_category_diagnostic(runner=object())

    def test_fit_stage_orchestration_has_no_outer_reader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root / "confirmatory")
            runner = cast(ProductionTaskRunner, SimpleNamespace(fingerprint="f" * 64))
            descriptor = {
                "run_id": "run",
                "diagnostic_runner_fingerprint": "f" * 64,
            }
            with (
                mock.patch(
                    "plategauge.same_category_diagnostic.load_diagnostic_context",
                    return_value=context,
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic._run_descriptor",
                    return_value=descriptor,
                ),
                mock.patch("plategauge.same_category_diagnostic._initialize_output"),
                mock.patch(
                    "plategauge.same_category_diagnostic._execute_task",
                    side_effect=[True, False],
                ) as execute,
                mock.patch("plategauge.same_category_diagnostic.FOLD_COUNT", 2),
                mock.patch(
                    "plategauge.post_evaluation._load_outer_task",
                    side_effect=AssertionError("fit opened outer"),
                ),
            ):
                result = fit_same_category_diagnostic(
                    runner=runner,
                    output_directory=root / "diagnostic",
                    dataset_root=root,
                )
            self.assertEqual(result["executed_tasks"], 1)
            self.assertEqual(result["resumed_tasks"], 1)
            self.assertFalse(result["outer_results_read"])
            self.assertEqual(execute.call_count, 2)


class DiagnosticTaskTests(unittest.TestCase):
    def test_partition_and_semantic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = _context(Path(directory))
            training, evaluation = _partition(context, 0)
            self.assertEqual(len(training), 2)
            self.assertEqual(len(evaluation), 2)
            task = _task(context, 0)
            predictions = _predictions(context, task)
            payload = _validate_predictions(context, task, predictions)
            self.assertEqual(payload["prediction_count"], 2)
            self.assertEqual(payload["seen_category_prediction_count"], 1)
            self.assertEqual(
                payload["interval_status"],
                "raw_uncalibrated_not_for_coverage_or_public_interval_claims",
            )
            bad = list(predictions)
            bad[0] = replace(
                bad[0],
                category_seen_in_training=not bad[0].category_seen_in_training,
            )
            with self.assertRaisesRegex(DataIntegrityError, "metadata differs"):
                _validate_predictions(context, task, bad)

    def test_task_recipe_is_bound_to_inner_selected_outer_spec(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = _context(Path(directory))
            task = _task(context, 1)
            source = _source_task(1)
            self.assertEqual(task["parameters"], source.parameters)
            self.assertEqual(
                task["source_outer_task_spec_sha256"],
                _canonical_sha256(source.to_dict()),
            )
            self.assertIn("raw_quantiles", task["interval_handling"])
            missing = replace(context, source_tasks=())
            with self.assertRaisesRegex(DataIntegrityError, "Missing unique"):
                _source_task_for_fold(missing, 1)

    def test_fold_without_seen_category_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root)
            singleton_context = replace(
                context,
                records=(_record(0, "001", 0.1), _record(1, "002", 0.2)),
                assignments={"sample-0": 0, "sample-1": 1},
            )
            task = _task(singleton_context, 0)
            predictions = _predictions(singleton_context, task)
            with self.assertRaisesRegex(DataIntegrityError, "no seen-category"):
                _validate_predictions(singleton_context, task, predictions)

    def test_task_execution_is_immutable_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root / "confirmatory")
            output = root / "diagnostic"
            output.mkdir()
            task = _task(context, 0)
            descriptor = {
                "run_id": "diagnostic-run",
                "diagnostic_runner_fingerprint": "f" * 64,
            }
            runner = cast(
                ProductionTaskRunner,
                SimpleNamespace(fingerprint="f" * 64, device="cpu", checkpoint_root=root),
            )
            quantiles = np.asarray([[0.0, 0.1, 0.2], [0.5, 0.6, 0.7]])
            with (
                mock.patch(
                    "plategauge.same_category_diagnostic._fit_predict",
                    return_value=quantiles,
                ) as fit,
                mock.patch(
                    "plategauge.post_evaluation._load_outer_task",
                    side_effect=AssertionError("fit stage opened an outer result"),
                ),
            ):
                self.assertTrue(_execute_task(context, output, descriptor, task, runner, root))
                self.assertFalse(_execute_task(context, output, descriptor, task, runner, root))
                self.assertEqual(fit.call_count, 1)
            task_dir = output / "tasks" / str(task["task_id"])
            _validate_completed_task(context, output, descriptor, task)
            predictions = task_dir / "workload" / "predictions.csv"
            predictions.write_text(predictions.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "hash/size"):
                _validate_completed_task(context, output, descriptor, task)


class DiagnosticSummaryTests(unittest.TestCase):
    def test_summary_uses_seen_categories_and_primary_minus_same_direction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = _context(Path(directory))
            diagnostic: list[DiagnosticPrediction] = []
            for fold in (0, 1):
                task = _task(context, fold)
                diagnostic.extend(_predictions(context, task))
            diagnostic.sort(key=lambda value: value.sample_id)
            primary = [
                SimpleNamespace(
                    sample_id=value.sample_id,
                    category=value.category,
                    target=value.target,
                    q50=min(1.0, value.raw_q50 + 0.2),
                )
                for value in diagnostic
            ]
            with (
                mock.patch("plategauge.same_category_diagnostic.EXPECTED_SEEN_ROWS", 2),
                mock.patch("plategauge.same_category_diagnostic.EXPECTED_SEEN_CATEGORIES", 1),
                mock.patch("plategauge.same_category_diagnostic.BOOTSTRAP_REPLICATES", 100),
            ):
                summary = build_summary_payload(
                    context,
                    diagnostic,
                    primary,
                    run_id="run",
                    diagnostic_sources=[],
                    primary_sources=[],
                )
            self.assertEqual(summary["coverage"]["seen_category_rows"], 2)
            self.assertEqual(summary["coverage"]["unseen_category_rows"], 2)
            matched = summary["matched_seen_category_estimand"]
            self.assertGreater(matched["observed_gap_category_disjoint_minus_same_category"], 0.0)
            self.assertEqual(summary["decision_role"], "context_only_no_release_gate")
            self.assertIn("not a causal estimate", summary["interpretation"]["scope"])
            self.assertNotIn("coverage", summary["matched_seen_category_estimand"])

    def test_validated_primary_loader_and_aggregate_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = _context(root / "confirmatory")
            loaded_items = []
            for fold, task in enumerate(context.source_tasks):
                result_path = root / f"result-{fold}.json"
                prediction_path = root / f"predictions-{fold}.csv"
                result_path.write_text("{}", encoding="utf-8")
                prediction_path.write_text("prediction", encoding="utf-8")
                loaded_items.append(
                    SimpleNamespace(
                        predictions=(
                            SimpleNamespace(
                                sample_id=f"primary-{fold}",
                                category="001",
                                target=0.5,
                                q50=0.5,
                            ),
                        ),
                        result_path=result_path,
                        prediction_path=prediction_path,
                        task=task,
                    )
                )
            with (
                mock.patch(
                    "plategauge.post_evaluation._load_outer_task",
                    side_effect=loaded_items,
                ) as load,
                mock.patch("plategauge.same_category_diagnostic.EXPECTED_VALID_ROWS", 5),
            ):
                primary, sources = _validated_primary_predictions(context)
            self.assertEqual(len(primary), 5)
            self.assertEqual(len(sources), 5)
            self.assertEqual(load.call_count, 5)

            runner = cast(ProductionTaskRunner, SimpleNamespace(fingerprint="f" * 64))
            descriptor = {
                "run_id": "diagnostic-run",
                "diagnostic_runner_fingerprint": "f" * 64,
            }
            task0 = _task(context, 0)
            task1 = _task(context, 1)
            predictions0 = _predictions(context, task0)
            predictions1 = _predictions(context, task1)
            summary = {
                "schema_version": "1.0",
                "kind": "secondary_same_category_diagnostic",
                "status": "complete",
            }
            output = root / "diagnostic"
            output.mkdir()
            for task in (task0, task1):
                task_dir = output / "tasks" / str(task["task_id"])
                (task_dir / "workload").mkdir(parents=True)
                (task_dir / "result.json").write_text("{}", encoding="utf-8")
                (task_dir / "workload" / "predictions.csv").write_text(
                    "predictions", encoding="utf-8"
                )
            with (
                mock.patch(
                    "plategauge.same_category_diagnostic.load_diagnostic_context",
                    return_value=context,
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic._run_descriptor",
                    return_value=descriptor,
                ),
                mock.patch("plategauge.same_category_diagnostic._initialize_output"),
                mock.patch("plategauge.same_category_diagnostic.FOLD_COUNT", 2),
                mock.patch(
                    "plategauge.same_category_diagnostic._task_spec",
                    side_effect=[task0, task1],
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic._validate_completed_task",
                    side_effect=[({}, predictions0), ({}, predictions1)],
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic._validated_primary_predictions",
                    return_value=(primary, sources),
                ),
                mock.patch(
                    "plategauge.same_category_diagnostic.build_summary_payload",
                    return_value=summary,
                ) as build,
            ):
                result = aggregate_same_category_diagnostic(
                    runner=runner,
                    output_directory=output,
                    dataset_root=root,
                )
            self.assertEqual(result["stage"], "aggregate")
            self.assertEqual(result["decision_role"], "context_only_no_release_gate")
            build.assert_called_once()


if __name__ == "__main__":
    unittest.main()
