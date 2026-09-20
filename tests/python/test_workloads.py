from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from PIL import Image

from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.folds import fold_for_category
from plategauge.orchestration import ExperimentTask, TaskRequest, WorkloadResult
from plategauge.schema import ManifestRecord, write_manifest
from plategauge.workloads import (
    ProductionTaskRunner,
    _build_dino_cache_identity,
    _build_neural_model,
    _cuda_device_index,
    _final_encoder_stages,
    _prediction_payload,
    _validate_dino_feature_arrays,
    _verify_checkpoint,
    _wrong_pair_records,
    execute_workload,
    sha256_file_bytes,
)


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
        observer_score=max(1, min(7, index + 1)),
        before_width=32,
        before_height=32,
        after_width=32,
        after_height=32,
        before_sha256=f"{index + 1:064x}",
        after_sha256=f"{index + 101:064x}",
        outer_fold=fold_for_category(category),
    )


def _task(
    *,
    workload: str,
    stage: str = "outer",
    training_folds: tuple[int, ...] = (0,),
    validation_folds: tuple[int, ...] = (),
    evaluation_fold: int | None = 1,
    parameters: dict[str, object] | None = None,
    expected: dict[str, int] | None = None,
) -> ExperimentTask:
    return ExperimentTask(
        task_id=f"test.{stage}.{workload}",
        stage=stage,
        workload=workload,
        outer_fold=evaluation_fold,
        training_folds=training_folds,
        validation_folds=validation_folds,
        evaluation_fold=evaluation_fold,
        parameters=dict(parameters or {}),
        expected_counts=dict(expected or {"training_count": 2, "prediction_count": 2}),
        required_artifact_roles=(
            ("oof_predictions",) if stage == "inner_tuning" else ("predictions",)
        ),
    )


class WorkloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "images").mkdir()
        self.records = [
            _record(0, "001", 0.2),
            _record(1, "001", 0.4),
            _record(2, "002", 0.6),
            _record(3, "002", 0.8),
        ]
        for index, _ in enumerate(self.records):
            before = Image.new("RGB", (32, 32), (80 + index, 100, 120))
            after = Image.new("RGB", (32, 32), (80 + index, 80 + index * 10, 100))
            before.save(self.root / f"images/before-{index}.png")
            after.save(self.root / f"images/after-{index}.png")
        self.manifest = self.root / "manifest.csv"
        write_manifest(self.records, self.manifest)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self, task: ExperimentTask) -> TaskRequest:
        return TaskRequest(
            schema_version="1.0",
            protocol_id="synthetic-protocol",
            manifest_path=str(self.manifest),
            dataset_root=str(self.root),
            task=task,
        )

    def execute_task(self, task: ExperimentTask) -> WorkloadResult:
        return execute_workload(
            self.request(task),
            self.workspace,
            checkpoint_root=self.root / "checkpoints",
            cache_root=self.root / "cache",
            device="cpu",
        )

    def test_median_and_observer_are_executable_and_write_ordered_predictions(self) -> None:
        median = self.execute_task(_task(workload="training_median"))
        self.assertEqual(median.payload["prediction_count"], 2)
        with (self.workspace / median.artifacts["predictions"]).open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        for value in (float(row["q50"]) for row in rows):
            self.assertAlmostEqual(value, 0.3)
        self.assertTrue(all(row["q05"] == row["q50"] == row["q95"] for row in rows))

        second_workspace = self.root / "observer"
        second_workspace.mkdir()
        result = execute_workload(
            self.request(_task(workload="observer_score_context_only")),
            second_workspace,
            checkpoint_root=self.root / "checkpoints",
            cache_root=self.root / "cache",
            device="cpu",
        )
        self.assertIn("macro_category_mae", result.payload)

    def test_prediction_payload_uses_full_precision_manifest_targets(self) -> None:
        records = [_record(0, "000", 1.0 / 3.0), _record(1, "000", 2.0 / 3.0)]
        medians = np.asarray([0.25, 0.75], dtype=np.float64)
        quantiles = np.repeat(medians[:, None], 3, axis=1)
        payload = _prediction_payload({"prediction_count": 2}, records, quantiles)
        expected = float(np.mean([abs((1.0 / 3.0) - 0.25), abs((2.0 / 3.0) - 0.75)]))
        self.assertEqual(payload["macro_category_mae"], expected)
        float32_metric = float(
            np.mean(
                np.abs(
                    np.asarray([1.0 / 3.0, 2.0 / 3.0], dtype=np.float32)
                    - medians
                )
            )
        )
        self.assertNotEqual(payload["macro_category_mae"], float32_metric)

    def test_handcrafted_ridge_tuning_and_outer_fit_execute_on_tiny_images(self) -> None:
        tuning = _task(
            workload="handcrafted_ridge",
            stage="inner_tuning",
            training_folds=(0, 1),
            validation_folds=(0, 1),
            evaluation_fold=None,
            parameters={"alphas": [0.1, 1.0]},
            expected={"development_count": 4},
        )
        result = self.execute_task(tuning)
        self.assertEqual(set(result.payload["fold_scores"]), {"0.1", "1"})
        self.assertTrue((self.workspace / "oof_predictions.csv").is_file())

        outer_workspace = self.root / "ridge-outer"
        outer_workspace.mkdir()
        outer = _task(workload="handcrafted_ridge", parameters={"alpha": 1.0})
        result = execute_workload(
            self.request(outer),
            outer_workspace,
            checkpoint_root=self.root / "checkpoints",
            cache_root=self.root / "cache",
            device="cpu",
        )
        self.assertEqual(result.payload["training_count"], 2)
        self.assertEqual(result.payload["prediction_count"], 2)

    def test_dispatches_heavy_approved_workloads_without_running_them(self) -> None:
        neural_result = WorkloadResult(
            payload={"training_count": 2, "prediction_count": 2},
            artifacts={"predictions": "predictions.csv"},
        )
        with mock.patch("plategauge.workloads._execute_neural", return_value=neural_result) as run:
            for workload in (
                "paired_mobilenet",
                "after_only_mobilenet",
                "fixed_within_category_wrong_pair",
                "paired_resnet50",
            ):
                task = _task(workload=workload)
                if workload == "fixed_within_category_wrong_pair":
                    task = _task(
                        workload=workload,
                        expected={"training_count": 2, "prediction_count": 2},
                    )
                self.execute_task(task)
            self.assertEqual(run.call_count, 4)

        dino_result = WorkloadResult(
            payload={"training_count": 2, "prediction_count": 2},
            artifacts={"predictions": "predictions.csv"},
        )
        with mock.patch("plategauge.workloads._execute_dino", return_value=dino_result) as run:
            self.execute_task(_task(workload="frozen_paired_dinov2"))
            run.assert_called_once()

    def test_scope_unknown_workload_and_checkpoint_tampering_fail_closed(self) -> None:
        bad_count = _task(
            workload="training_median",
            expected={"training_count": 99, "prediction_count": 2},
        )
        with self.assertRaisesRegex(DataIntegrityError, "training scope"):
            self.execute_task(bad_count)
        with self.assertRaisesRegex(DataIntegrityError, "No approved workload"):
            self.execute_task(_task(workload="invented_model"))

        checkpoint = self.root / "checkpoints" / "tiny" / "revision" / "model.bin"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(b"verified")
        metadata = {
            "checkpoint": "tiny",
            "revision": "revision",
            "filename": "model.bin",
            "size_bytes": len(b"verified"),
            "sha256": "0" * 64,
        }
        with self.assertRaisesRegex(DataIntegrityError, "SHA-256"):
            _verify_checkpoint(metadata, self.root / "checkpoints")

    def test_execute_scope_preserves_singletons_for_wrong_pair_fallback(self) -> None:
        scoped_records = [
            _record(20, "001", 0.2),
            _record(21, "005", 0.3),
            _record(22, "002", 0.4),
            _record(23, "008", 0.5),
        ]
        expected = WorkloadResult(
            payload={"training_count": 2, "prediction_count": 2},
            artifacts={"predictions": "predictions.csv"},
        )
        with (
            mock.patch("plategauge.workloads.read_manifest", return_value=scoped_records),
            mock.patch("plategauge.workloads._execute_neural", return_value=expected) as neural,
        ):
            result = self.execute_task(_task(workload="fixed_within_category_wrong_pair"))
        self.assertIs(result, expected)
        call = neural.call_args
        self.assertEqual(len(call.args[4]), 2)
        self.assertEqual(len(call.args[5]), 2)

    def test_wrong_pair_mapping_and_production_runner_identity_are_deterministic(self) -> None:
        wrong, pairing_rows, fallback_ids = _wrong_pair_records(
            self.records, scope="evaluation"
        )
        self.assertEqual(len(wrong), 4)
        self.assertNotEqual(wrong[0].after_path, self.records[0].after_path)
        self.assertEqual(len(pairing_rows), 4)
        self.assertEqual(fallback_ids, ())
        runner_a = ProductionTaskRunner(
            checkpoint_root=self.root / "checkpoints",
            cache_root=self.root / "cache",
            device="cpu",
        )
        runner_b = ProductionTaskRunner(
            checkpoint_root=self.root / "checkpoints",
            cache_root=self.root / "cache",
            device="cpu",
        )
        self.assertEqual(runner_a.fingerprint, runner_b.fingerprint)
        self.assertEqual(len(runner_a.fingerprint), 64)
        torch_runtime = runner_a.environment["runtime"]["torch_runtime"]
        self.assertGreater(torch_runtime["num_threads"], 0)
        self.assertGreater(torch_runtime["num_interop_threads"], 0)
        self.assertEqual(
            set(torch_runtime["thread_environment"]),
            {"OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"},
        )
        with mock.patch(
            "plategauge.workloads.sha256_file",
            side_effect=lambda path: (
                "f" * 64 if Path(path).name == "metrics.py" else sha256_file(path)
            ),
        ):
            tampered = ProductionTaskRunner(
                checkpoint_root=self.root / "checkpoints",
                cache_root=self.root / "cache",
                device="cpu",
            )
        self.assertNotEqual(runner_a.fingerprint, tampered.fingerprint)

    def test_cuda_runner_fails_fast_without_cublas_determinism_environment(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            cpu = ProductionTaskRunner(device="cpu")
            self.assertIsNone(cpu.environment["runtime"]["cublas_workspace_config"])
            with self.assertRaisesRegex(DataIntegrityError, "CUBLAS_WORKSPACE_CONFIG"):
                ProductionTaskRunner(device="cuda")
        with mock.patch.dict(
            os.environ, {"CUBLAS_WORKSPACE_CONFIG": ":4096:8"}, clear=True
        ):
            cuda = ProductionTaskRunner(device="cuda")
            self.assertEqual(
                cuda.environment["runtime"]["cublas_workspace_config"], ":4096:8"
            )

    def test_explicit_cuda_index_is_not_replaced_by_current_device(self) -> None:
        current_device = mock.Mock(return_value=0)
        fake_torch = SimpleNamespace(
            device=lambda value: SimpleNamespace(
                type=value.split(":", maxsplit=1)[0],
                index=int(value.split(":", maxsplit=1)[1]) if ":" in value else None,
            ),
            cuda=SimpleNamespace(current_device=current_device),
        )
        self.assertEqual(_cuda_device_index(fake_torch, "cuda:1"), 1)
        current_device.assert_not_called()
        self.assertEqual(_cuda_device_index(fake_torch, "cuda"), 0)
        current_device.assert_called_once()

    def test_wrong_pair_singleton_uses_same_fold_fallback_and_stage_helper_is_explicit(self) -> None:
        singleton = _record(9, "008", 0.5)
        donor_a = _record(10, "002", 0.3)
        donor_b = _record(11, "002", 0.4)
        paired, pairing_rows, fallback_ids = _wrong_pair_records(
            [singleton, donor_a, donor_b], scope="evaluation"
        )
        self.assertEqual(len(fallback_ids), 2)
        self.assertIn(singleton.sample_id, fallback_ids)
        self.assertEqual(len(pairing_rows), 3)
        self.assertEqual(
            {record.after_path for record in paired},
            {singleton.after_path, donor_a.after_path, donor_b.after_path},
        )
        self.assertTrue(
            all(record.after_path != original.after_path for record, original in zip(paired, (singleton, donor_a, donor_b), strict=True))
        )
        originals = {record.sample_id: record for record in (singleton, donor_a, donor_b)}
        rows_by_id = {row["sample_id"]: row for row in pairing_rows}
        for record in paired:
            row = rows_by_id[record.sample_id]
            donor = originals[row["source_sample_id"]]
            self.assertEqual(record.after_path, donor.after_path)
            self.assertEqual(record.after_sha256, donor.after_sha256)
            self.assertEqual((record.after_width, record.after_height), (donor.after_width, donor.after_height))

        class StageContainer:
            def __init__(self, values: list[object]) -> None:
                self.values = values

            def children(self):
                return iter(self.values)

        class MobileEncoder:
            blocks = StageContainer(["a", "b", "c"])
            features = None

        class ResNetEncoder:
            layer1 = "a"
            layer2 = "b"
            layer3 = "c"
            layer4 = "d"

        self.assertEqual(_final_encoder_stages(MobileEncoder()), ["b", "c"])
        self.assertEqual(_final_encoder_stages(ResNetEncoder()), ["c", "d"])

    def test_neural_head_construction_is_seeded_before_every_build(self) -> None:
        task = _task(
            workload="paired_mobilenet",
            parameters={
                "configuration": "M1",
                "seed": 20260919,
                "dropout": 0.2,
                "pretrained_artifact": {
                    "checkpoint": "mock",
                    "revision": "mock",
                    "filename": "model.safetensors",
                    "size_bytes": 1,
                    "sha256": "0" * 64,
                },
            },
        )
        weights = self.root / "model.safetensors"
        with (
            mock.patch("plategauge.workloads._verify_checkpoint", return_value=weights),
            mock.patch(
                "plategauge.workloads.build_paired_model",
                side_effect=lambda **_kwargs: float(np.random.random()),
            ),
        ):
            first, _, _ = _build_neural_model(task, self.root)
            second, _, _ = _build_neural_model(task, self.root)
        self.assertEqual(first, second)

    def test_dino_execution_seeds_before_loading_or_reusing_features(self) -> None:
        task = _task(
            workload="frozen_paired_dinov2",
            parameters={
                "seed": 20260919,
                "alpha": 1.0,
                "pretrained_artifact": {},
                "embedding_batch_size_cpu": 8,
                "embedding_batch_size_cuda": 16,
            },
        )
        features = {
            record.sample_id: np.asarray([index, index**2, 1.0], dtype=np.float32)
            for index, record in enumerate(self.records)
        }
        workspace = self.root / "dino-seed"
        workspace.mkdir()
        with (
            mock.patch("plategauge.workloads.seed_everything") as seed,
            mock.patch(
                "plategauge.workloads._dino_feature_cache",
                return_value=(features, {"cache_identity_sha256": "a" * 64}),
            ) as cache,
        ):
            result = execute_workload(
                self.request(task),
                workspace,
                checkpoint_root=self.root / "checkpoints",
                cache_root=self.root / "cache",
                device="cpu",
            )
        seed.assert_called_once_with(20260919)
        cache.assert_called_once()
        self.assertTrue((workspace / result.artifacts["predictions"]).is_file())

    def test_dino_cache_identity_binds_runtime_preprocessing_source_and_shape(self) -> None:
        base_arguments = {
            "checkpoint_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "versions": {
                "timm": "1.0.20",
                "torch": "2.10.0",
                "torchvision": "0.25.0",
                "numpy": "2.4.3",
                "Pillow": "12.1.1",
                "cuda": "None",
                "cudnn": "None",
            },
            "hardware": {"machine": "test", "device_type": "cpu"},
            "determinism": {
                "seed": 20260919,
                "deterministic_algorithms": True,
                "cudnn_benchmark": False,
                "cudnn_deterministic": True,
            },
            "embedding_batch_size": 8,
            "preprocessing": {"input_size": [3, 518, 518], "interpolation": "bicubic"},
            "implementation_sha256": "c" * 64,
        }
        identity = _build_dino_cache_identity(**base_arguments)

        def digest(value: dict[str, object]) -> str:
            return sha256_file_bytes(
                json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )

        for changed in (
            {"versions": {**base_arguments["versions"], "timm": "1.0.21"}},
            {"preprocessing": {"input_size": [3, 518, 518], "interpolation": "bilinear"}},
            {"implementation_sha256": "d" * 64},
            {
                "determinism": {
                    **base_arguments["determinism"],
                    "seed": 20260920,
                }
            },
        ):
            self.assertNotEqual(
                digest(identity),
                digest(_build_dino_cache_identity(**(base_arguments | changed))),
            )

        ids = [f"sample-{index:04d}" for index in range(514)]
        features = np.zeros((514, 1536), dtype=np.float32)
        feature_hash = sha256_file_bytes(features.tobytes(order="C"))
        self.assertEqual(
            _validate_dino_feature_arrays(
                expected_ids=ids,
                observed_ids=ids,
                features=features,
                recorded_identity_sha256="e" * 64,
                expected_identity_sha256="e" * 64,
                recorded_features_sha256=feature_hash,
            ),
            feature_hash,
        )
        with self.assertRaisesRegex(DataIntegrityError, "identity, shape, or contents"):
            _validate_dino_feature_arrays(
                expected_ids=ids,
                observed_ids=ids,
                features=features[:, :-1],
                recorded_identity_sha256="e" * 64,
                expected_identity_sha256="e" * 64,
                recorded_features_sha256=feature_hash,
            )


if __name__ == "__main__":
    unittest.main()
