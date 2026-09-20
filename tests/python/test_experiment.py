from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from plategauge.cli import main
from plategauge.experiment import experiment_preflight, experiment_task_matrix, run_experiment
from plategauge.folds import EXPECTED_FOLD_COUNTS


class ExperimentGateTests(unittest.TestCase):
    def write_audit(self, directory: str, *, passed: bool) -> Path:
        path = Path(directory) / "audit.json"
        payload = {
            "schema_version": "1.0",
            "passed": passed,
            "issues": [] if passed else ["duplicates cross folds"],
            "workbook_rows": 678,
            "matched_pairs": 524,
            "missing_image_rows": 154,
            "valid_pairs": 514,
            "invalid_mass_pairs": 10,
            "valid_categories": 34,
            "files_verified": True,
            "hashes_verified": True,
            "expected_counts_match": True,
            "cross_fold_duplicate_components": 0 if passed else 6,
            "fold_counts": {str(key): value for key, value in EXPECTED_FOLD_COUNTS.items()},
        }
        path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        return path

    def test_task_matrix_covers_five_by_four_by_two(self) -> None:
        matrix = experiment_task_matrix()
        self.assertEqual(len(matrix), 40)
        self.assertEqual({row["configuration"] for row in matrix}, {"M1", "M2"})

    def test_failed_data_gate_blocks_all_training(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = self.write_audit(directory, passed=False)
            result = run_experiment(audit)
        self.assertEqual(result.status, "blocked")
        self.assertIn("duplicates cross folds", result.blocker or "")
        self.assertEqual(len(result.inner_runs), 40)

    def test_passed_gate_supports_dry_run_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = self.write_audit(directory, passed=True)
            self.assertEqual(experiment_preflight(audit).status, "ready")
            self.assertEqual(run_experiment(audit, dry_run=True).status, "ready")
            with self.assertRaisesRegex(RuntimeError, "preflight-only"):
                run_experiment(audit)

    def test_claimed_pass_without_hash_verification_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = self.write_audit(directory, passed=True)
            payload = json.loads(audit.read_text(encoding="utf-8"))
            payload["hashes_verified"] = False
            audit.write_text(json.dumps(payload), encoding="utf-8")
            result = experiment_preflight(audit)
        self.assertEqual(result.status, "blocked")
        self.assertIn("hashes_verified", result.blocker or "")

    def test_cli_returns_nonzero_for_blocked_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = self.write_audit(directory, passed=False)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(["run-experiment", "--audit-report", str(audit)])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
