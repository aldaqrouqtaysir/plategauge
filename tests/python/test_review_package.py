from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from plategauge.errors import DataIntegrityError
from plategauge.review_package import (
    PRIVATE_OR_LOCAL_FILES,
    REQUIRED_SOURCE_PATHS,
    create_gate_d_review_package,
    prospective_source_files,
    validate_source_inventory,
    write_deterministic_zip,
)


class ReviewPackageTests(unittest.TestCase):
    PRIVATE_BOUNDARY_FILES: ClassVar[frozenset[str]] = frozenset(
        {
            "docs/AI_ASSISTANCE_LOG.md",
            "docs/APPLICATION_CRITICAL_PATH.md",
            "docs/APPLICATION_TIMELINE.md",
            "docs/CHANGELOG.md",
            "docs/CONSTRAINTS.md",
            "docs/CONTINUATION_PROMPT.md",
            "docs/CONTRIBUTION_RECORD.md",
            "docs/DECISION_LOG.md",
            "docs/FINAL_AUDIT.md",
            "docs/FINALIST_COMPARISON.md",
            "docs/IDEA_LONG_LIST.md",
            "docs/IDEA_SCORECARD.csv",
            "docs/MBZUAI_ALIGNMENT.md",
            "docs/MILESTONES.md",
            "docs/NEXT_ACTION.md",
            "docs/PROBLEM_DISCOVERY.md",
            "docs/PROBLEM_EVIDENCE_TABLE.csv",
            "docs/PROFILE_GAP_MAP.md",
            "docs/PROJECT_TRACKER.md",
            "docs/RISK_REGISTER.md",
            "docs/SOURCE_REGISTER.md",
            "docs/STATE.md",
            "release/applicant-mastery-signoff.json",
            "reports/media/plategauge-full-page-review.png",
            "reports/release/GATE_D_LOCAL_AUDIT_SUMMARY.md",
            "reports/release/gate-d-local-candidate-audit.json",
        }
    )

    def _git_init(self, root: Path) -> None:
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=root,
            check=True,
            capture_output=True,
        )

    def _write(self, root: Path, relative: str, data: bytes = b"evidence\n") -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _minimal_candidate(self, root: Path) -> None:
        self._write(
            root,
            ".gitignore",
            b"docs/application/\nartifacts/checkpoints/\nweb/dist/\n",
        )
        for relative in REQUIRED_SOURCE_PATHS:
            self._write(root, relative)
        self._write(
            root,
            "reports/experiments/confirmatory/tasks/task-a/task.json",
            b"{}\n",
        )
        self._write(
            root,
            "reports/experiments/confirmatory/tasks/task-a/result.json",
            b"{}\n",
        )
        self._write(
            root,
            "reports/experiments/confirmatory/tasks/task-a/workload/predictions.csv",
            b"sample_id,target\na,0\n",
        )

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_current_candidate_includes_all_non_checkpoint_task_evidence(self) -> None:
        files = prospective_source_files(self.repo_root)
        report = validate_source_inventory(self.repo_root, files)
        relatives = {path.relative_to(self.repo_root).as_posix() for path in files}
        self.assertEqual(report["taskCsvJsonCount"], 292)
        self.assertEqual(report["workloadCsvJsonCount"], 100)
        self.assertEqual(report["workloadCsvCount"], 100)
        self.assertIn(
            "reports/experiments/confirmatory/tasks/outer.fold-4.paired_mobilenet/"
            "workload/predictions.csv",
            relatives,
        )
        self.assertNotIn("docs/application/PORTFOLIO_ENTRY.md", relatives)
        self.assertFalse(any(path.startswith("artifacts/checkpoints/") for path in relatives))
        self.assertFalse(any(path.startswith("web/coverage/") for path in relatives))

    def test_private_boundary_is_ignored_and_fail_closed(self) -> None:
        self.assertTrue(self.PRIVATE_BOUNDARY_FILES.issubset(PRIVATE_OR_LOCAL_FILES))
        for relative in sorted(self.PRIVATE_BOUNDARY_FILES):
            result = subprocess.run(
                ["git", "check-ignore", "--quiet", "--no-index", relative],
                cwd=self.repo_root,
                check=False,
                capture_output=True,
            )
            self.assertEqual(0, result.returncode, relative)

    def test_force_added_private_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            self._git_init(root)
            self._minimal_candidate(root)
            private = self._write(root, "docs/DECISION_LOG.md", b"private\n")
            subprocess.run(
                ["git", "add", "-f", private.relative_to(root).as_posix()],
                cwd=root,
                check=True,
                capture_output=True,
            )
            with self.assertRaisesRegex(DataIntegrityError, "entered the prospective public tree"):
                prospective_source_files(root)

    def test_ignored_workload_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            self._git_init(root)
            self._minimal_candidate(root)
            with (root / ".gitignore").open("ab") as handle:
                handle.write(b"reports/experiments/**/workload/*.csv\n")
            files = prospective_source_files(root)
            with self.assertRaisesRegex(DataIntegrityError, "ignored or omitted"):
                validate_source_inventory(root, files)

    def test_zip_bytes_ignore_source_mtime_and_have_normalized_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            first = self._write(root, "a.txt", b"alpha\n")
            second = self._write(root, "nested/b.txt", b"beta\n")
            one = Path(directory) / "one.zip"
            two = Path(directory) / "two.zip"
            first_report = write_deterministic_zip(one, root, [second, first], prefix="tree")
            os.utime(first, (2_000_000_000, 2_000_000_000))
            os.utime(second, (1_000_000_000, 1_000_000_000))
            second_report = write_deterministic_zip(two, root, [first, second], prefix="tree")
            self.assertEqual(one.read_bytes(), two.read_bytes())
            self.assertEqual(first_report["sha256"], second_report["sha256"])
            with zipfile.ZipFile(one) as archive:
                self.assertEqual(archive.namelist(), ["tree/a.txt", "tree/nested/b.txt"])
                self.assertTrue(
                    all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
                )

    def test_full_draft_package_is_repeatable_and_manifested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "repo"
            outputs = base / "outputs"
            root.mkdir()
            outputs.mkdir()
            self._git_init(root)
            self._minimal_candidate(root)
            self._write(root, "docs/application/private.md", b"private\n")
            self._write(root, "artifacts/checkpoints/model.pt", b"checkpoint\n")
            self._write(root, "web/dist/index.html", b"<html></html>\n")
            self._write(outputs, "review.md", b"review\n")
            static_audit = {
                "status": "passed",
                "fileCount": 1,
                "inventorySha256": "a" * 64,
            }
            web_evidence = {"status": "passed", "sha256": "b" * 64}
            with (
                patch(
                    "plategauge.review_package.audit_release_bundle",
                    return_value=static_audit,
                ),
                patch(
                    "plategauge.review_package.verify_web_benchmark_evidence",
                    return_value=web_evidence,
                ),
            ):
                first = create_gate_d_review_package(root, outputs, "2026-09-20", ["review.md"])
                source_bytes = (outputs / first["source"]["filename"]).read_bytes()
                static_bytes = (outputs / first["static"]["filename"]).read_bytes()
                manifest_bytes = (outputs / first["manifest"]).read_bytes()
                second = create_gate_d_review_package(root, outputs, "2026-09-20", ["review.md"])
            self.assertEqual(source_bytes, (outputs / second["source"]["filename"]).read_bytes())
            self.assertEqual(static_bytes, (outputs / second["static"]["filename"]).read_bytes())
            self.assertEqual(manifest_bytes, (outputs / second["manifest"]).read_bytes())
            with zipfile.ZipFile(outputs / first["source"]["filename"]) as archive:
                names = set(archive.namelist())
            self.assertIn(
                "plategauge/reports/experiments/confirmatory/tasks/task-a/workload/predictions.csv",
                names,
            )
            self.assertNotIn("plategauge/docs/application/private.md", names)
            self.assertNotIn("plategauge/artifacts/checkpoints/model.pt", names)

    def test_outputs_inside_public_repo_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            with self.assertRaisesRegex(DataIntegrityError, "outside"):
                create_gate_d_review_package(root, root / "outputs", "2026-09-20", [])


if __name__ == "__main__":
    unittest.main()
