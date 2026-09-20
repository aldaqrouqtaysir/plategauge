from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.release_artifacts import (
    FrozenFinalArtifact,
    canonical_json_sha256,
    read_json_object,
    validate_frozen_final_artifact,
    write_immutable_json,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ReleaseArtifactTests(unittest.TestCase):
    def _frozen_tree(self, root: Path) -> tuple[dict[str, Path], dict[str, object]]:
        inputs = {
            "audit_report": root / "audit.json",
            "manifest": root / "manifest.csv",
            "experiment_config": root / "experiment.toml",
            "frozen_folds": root / "folds.json",
        }
        inputs["audit_report"].write_text("{}\n", encoding="utf-8")
        inputs["manifest"].write_text("manifest\n", encoding="utf-8")
        inputs["frozen_folds"].write_text("{}\n", encoding="utf-8")
        inputs["experiment_config"].write_text(
            "[configuration.M1]\ndropout = 0.2\n[configuration.M2]\ndropout = 0.4\n",
            encoding="utf-8",
        )
        input_hashes = {name: sha256_file(path) for name, path in inputs.items()}
        protocol_id = "1" * 64
        runner_fingerprint = "2" * 64
        experiment = root / "experiment"

        outer_sources: list[dict[str, object]] = []
        policies: list[dict[str, object]] = []
        for fold in range(5):
            task_id = f"inner.source.{fold}"
            source_result = experiment / "tasks" / task_id / "result.json"
            _write_json(source_result, {"fold": fold})
            policy = {
                "interval_correction": 0.01 + fold * 0.001,
                "abstention_threshold": 0.20 + fold * 0.01,
            }
            policies.append(policy)
            outer = {
                "schema_version": "1.0",
                "kind": "outer_selection",
                "information_boundary": "inner_development_predictions_only",
                "protocol_id": protocol_id,
                "outer_fold": fold,
                "primary": {"configuration": "M1", "epoch": fold + 2},
                "uncertainty_policy": policy,
                "sources": [{"task_id": task_id, "sha256": sha256_file(source_result)}],
            }
            outer_path = experiment / "selections" / f"outer-{fold}.json"
            _write_json(outer_path, outer)
            outer_sources.append({"outer_fold": fold, "sha256": sha256_file(outer_path)})
        included = [
            {
                "outer_fold": fold,
                "selected_primary_configuration": "M1",
                "interval_correction": policy["interval_correction"],
                "abstention_threshold": policy["abstention_threshold"],
            }
            for fold, policy in enumerate(policies)
        ]
        final = {
            "schema_version": "1.0",
            "kind": "final_deploy_choice",
            "information_boundary": "inner_selections_only_no_outer_metrics",
            "protocol_id": protocol_id,
            "configuration": "M1",
            "epoch": 4,
            "uncertainty_policy": {
                "method": "median_of_inner_only_outer_policies_matching_final_configuration",
                "selection_rule": (
                    "include_only_outer_selections_whose_selected_primary_configuration_"
                    "matches_the_final_modal_configuration"
                ),
                "final_configuration": "M1",
                "minimum_matching_outer_selections": 3,
                "included_outer_selections": included,
                "excluded_outer_selections": [],
                "interval_correction": 0.012,
                "abstention_threshold": 0.22,
            },
            "outer_selection_sources": outer_sources,
        }
        _write_json(experiment / "selections" / "final.json", final)

        parameters = {
            "configuration": "M1",
            "epoch": 4,
            "dropout": 0.2,
            "encoder_learning_rate": 3e-5,
            "head_learning_rate": 3e-4,
            "batch_size": 32,
            "training_scope": "all_514_valid_pairs",
            "selection_source": "inner_only_modal_configuration_and_median_epoch",
            "uncertainty_policy": final["uncertainty_policy"],
        }
        task = {
            "task_id": "final.deploy.paired_mobilenet",
            "stage": "final",
            "workload": "paired_mobilenet",
            "outer_fold": None,
            "training_folds": [0, 1, 2, 3, 4],
            "validation_folds": [],
            "evaluation_fold": None,
            "parameters": parameters,
            "expected_counts": {"training_count": 514},
            "required_artifact_roles": ["model_checkpoint"],
        }
        task_directory = experiment / "tasks" / "final.deploy.paired_mobilenet"
        _write_json(task_directory / "task.json", task)
        checkpoint = task_directory / "workload" / "model_checkpoint.pt"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(b"checkpoint-test-bytes")
        payload = {"training_count": 514}
        result = {
            "schema_version": "1.0",
            "status": "complete",
            "task_id": task["task_id"],
            "protocol_id": protocol_id,
            "task_spec_sha256": canonical_json_sha256(task),
            "runner_fingerprint": runner_fingerprint,
            "payload": payload,
            "payload_sha256": canonical_json_sha256(payload),
            "artifacts": [
                {
                    "role": "model_checkpoint",
                    "path": "workload/model_checkpoint.pt",
                    "size_bytes": checkpoint.stat().st_size,
                    "sha256": sha256_file(checkpoint),
                }
            ],
        }
        _write_json(task_directory / "result.json", result)
        run_core = {
            "schema_version": "1.0",
            "protocol": {"protocol_id": protocol_id, "input_hashes": dict(sorted(input_hashes.items()))},
            "runner_fingerprint": runner_fingerprint,
            "dataset_verification": {"record_count": 524},
        }
        _write_json(experiment / "run.json", run_core | {"run_id": canonical_json_sha256(run_core)})
        context: dict[str, object] = {
            "protocol_id": protocol_id,
            "input_hashes": input_hashes,
            "task": task,
            "experiment": experiment,
        }
        return inputs, context

    def test_validates_exact_reconstructed_final_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, context = self._frozen_tree(root)
            protocol = SimpleNamespace(
                protocol_id=context["protocol_id"], input_hashes=context["input_hashes"]
            )
            preflight = SimpleNamespace(status="ready", blocker=None)
            canonical_task_value = json.loads(json.dumps(context["task"]))
            for field in ("training_folds", "validation_folds", "required_artifact_roles"):
                canonical_task_value[field] = tuple(canonical_task_value[field])
            canonical_task = SimpleNamespace(to_dict=lambda: canonical_task_value)
            with (
                patch(
                    "plategauge.release_artifacts.protocol_preflight",
                    return_value=(preflight, protocol),
                ),
                patch(
                    "plategauge.release_artifacts.build_final_task",
                    return_value=canonical_task,
                ),
            ):
                artifact = validate_frozen_final_artifact(
                    experiment_directory=context["experiment"],
                    audit_report_path=inputs["audit_report"],
                    manifest_path=inputs["manifest"],
                    config_path=inputs["experiment_config"],
                    folds_path=inputs["frozen_folds"],
                )
            self.assertIsInstance(artifact, FrozenFinalArtifact)
            self.assertEqual(artifact.configuration, "M1")
            self.assertEqual(artifact.epoch, 4)
            self.assertEqual(artifact.interval_correction, 0.012)
            self.assertEqual(len(artifact.hashes["checkpoint_sha256"]), 64)

    def test_rejects_coordinated_parameter_tamper_even_with_rehashed_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, context = self._frozen_tree(root)
            canonical = json.loads(json.dumps(context["task"]))
            tampered = json.loads(json.dumps(context["task"]))
            tampered["parameters"]["batch_size"] = 64
            task_path = (
                Path(str(context["experiment"]))
                / "tasks/final.deploy.paired_mobilenet/task.json"
            )
            result_path = task_path.with_name("result.json")
            _write_json(task_path, tampered)
            result = read_json_object(result_path)
            result["task_spec_sha256"] = canonical_json_sha256(tampered)
            _write_json(result_path, result)
            protocol = SimpleNamespace(
                protocol_id=context["protocol_id"], input_hashes=context["input_hashes"]
            )
            with (
                patch(
                    "plategauge.release_artifacts.protocol_preflight",
                    return_value=(SimpleNamespace(status="ready", blocker=None), protocol),
                ),
                patch(
                    "plategauge.release_artifacts.build_final_task",
                    return_value=SimpleNamespace(to_dict=lambda: canonical),
                ),
                self.assertRaisesRegex(DataIntegrityError, "canonically reconstructed"),
            ):
                validate_frozen_final_artifact(
                    experiment_directory=context["experiment"],
                    audit_report_path=inputs["audit_report"],
                    manifest_path=inputs["manifest"],
                    config_path=inputs["experiment_config"],
                    folds_path=inputs["frozen_folds"],
                )

    def test_json_helpers_are_canonical_and_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            payload = {"z": 1, "a": [2, 3]}
            write_immutable_json(path, payload)
            self.assertEqual(read_json_object(path), payload)
            self.assertEqual(len(canonical_json_sha256(payload)), 64)
            with self.assertRaisesRegex(DataIntegrityError, "already exists"):
                write_immutable_json(path, payload)
            with self.assertRaises(DataIntegrityError):
                canonical_json_sha256({"bad": float("nan")})


if __name__ == "__main__":
    unittest.main()
