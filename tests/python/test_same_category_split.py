from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from plategauge.same_category_split import (
    SplitRow,
    assign_same_category_folds,
    build_split_artifact,
    sha256_file,
    validate_assignment,
    validate_split_artifact,
    write_immutable_json,
)


class SameCategoryAssignmentTests(unittest.TestCase):
    def test_assignment_is_deterministic_balanced_and_duplicate_atomic(self) -> None:
        rows = [
            SplitRow("a1", "001", "shared"),
            SplitRow("a2", "001", "shared"),
            SplitRow("b1", "002", "shared"),
            *[SplitRow(f"a{index}", "001", "") for index in range(3, 13)],
            *[SplitRow(f"b{index}", "002", "") for index in range(2, 10)],
        ]
        first = assign_same_category_folds(rows, 20260919)
        second = assign_same_category_folds(list(reversed(rows)), 20260919)
        self.assertEqual(first, second)
        self.assertEqual(first["a1"], first["a2"])
        self.assertEqual(first["a1"], first["b1"])
        validation = validate_assignment(rows, first)
        self.assertTrue(validation["passed"])

    def test_small_categories_populate_only_available_atomic_folds(self) -> None:
        rows = [SplitRow("one", "000", ""), SplitRow("two", "005", "")]
        assignments = assign_same_category_folds(rows, 7)
        validation = validate_assignment(rows, assignments)
        self.assertTrue(validation["passed"])
        for summary in validation["category_summary"].values():
            self.assertEqual(summary["populated_folds"], 1)
            self.assertEqual(summary["maximum_populatable_folds"], 1)

    def test_cross_fold_duplicate_tamper_fails(self) -> None:
        rows = [SplitRow("a", "001", "dup"), SplitRow("b", "002", "dup")]
        validation = validate_assignment(rows, {"a": 0, "b": 1})
        self.assertFalse(validation["passed"])
        self.assertFalse(validation["checks"]["duplicate_components_atomic"])


class SameCategoryArtifactTests(unittest.TestCase):
    @staticmethod
    def _write_fixture(root: Path) -> tuple[Path, Path]:
        manifest = root / "manifest.csv"
        fields = ["sample_id", "category", "duplicate_group", "is_valid"]
        with manifest.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in (
                {"sample_id": "a", "category": "001", "duplicate_group": "", "is_valid": "true"},
                {"sample_id": "b", "category": "001", "duplicate_group": "", "is_valid": "true"},
                {"sample_id": "x", "category": "999", "duplicate_group": "", "is_valid": "false"},
            ):
                writer.writerow(row)
        manifest_hash = sha256_file(manifest)
        run = root / "run.json"
        run.write_text(
            json.dumps(
                {
                    "run_id": "run-id",
                    "runner_fingerprint": "runner-id",
                    "protocol": {
                        "confirmatory_seed": 20260919,
                        "protocol_id": "protocol-id",
                        "input_hashes": {"manifest": manifest_hash, "config": "c" * 64},
                    },
                    "runner_environment": {"sources": {"training.py": "a" * 64}},
                }
            ),
            encoding="utf-8",
        )
        return manifest, run

    def test_build_validate_and_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, run = self._write_fixture(root)
            artifact = build_split_artifact(manifest, run)
            self.assertTrue(validate_split_artifact(artifact, manifest, run)["passed"])
            self.assertNotIn("confirmatory_run_id", artifact["bindings"])
            self.assertNotIn("confirmatory_runner_fingerprint", artifact["bindings"])
            self.assertNotIn("execution_source_hashes", artifact["bindings"])
            original_fold = artifact["assignments"][0]["diagnostic_fold"]
            artifact["assignments"][0]["diagnostic_fold"] = (original_fold + 1) % 5
            self.assertFalse(validate_split_artifact(artifact, manifest, run)["passed"])

    def test_runner_identity_change_does_not_change_data_split(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, run = self._write_fixture(root)
            first = build_split_artifact(manifest, run)
            payload = json.loads(run.read_text(encoding="utf-8"))
            payload["run_id"] = "a-new-run"
            payload["runner_fingerprint"] = "a-new-runner"
            payload["runner_environment"]["sources"]["training.py"] = "b" * 64
            run.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(first, build_split_artifact(manifest, run))

    def test_manifest_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, run = self._write_fixture(root)
            manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Manifest hash"):
                build_split_artifact(manifest, run)

    def test_immutable_writer_refuses_changed_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frozen.json"
            write_immutable_json(path, {"value": 1})
            write_immutable_json(path, {"value": 1})
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                write_immutable_json(path, {"value": 2})


if __name__ == "__main__":
    unittest.main()
