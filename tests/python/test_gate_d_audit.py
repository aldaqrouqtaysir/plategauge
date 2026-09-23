from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plategauge.gate_d_audit import (
    REVIEWED_CAMERA_SCREENSHOT_SHA256,
    _raw_data_candidates,
    audit_gate_d_candidate,
)


class CameraScreenshotBoundaryTests(unittest.TestCase):
    def test_only_two_reviewed_paths_and_hashes_are_pinned(self) -> None:
        self.assertEqual(
            REVIEWED_CAMERA_SCREENSHOT_SHA256,
            {
                "reports/media/camera-home-2026-09-23.png": (
                    "63ccb2605da0a5c5096240bf7e085c229f13d2189b7178a6102933a94a8153e1"
                ),
                "reports/media/camera-idle-2026-09-23.png": (
                    "ee0da4e35f68e7e06fda1193637ba628dabf2348046ee60b7c6dd29b3fcd56ab"
                ),
            },
        )

    def test_reviewed_paths_require_their_own_matching_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, expected in REVIEWED_CAMERA_SCREENSHOT_SHA256.items():
                with self.subTest(relative=relative):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"synthetic fixture, not an image")
                    with patch("plategauge.gate_d_audit.sha256_file", return_value=expected) as digest:
                        self.assertEqual(_raw_data_candidates(root, [path]), [])
                        digest.assert_called_once_with(path)
                    with patch("plategauge.gate_d_audit.sha256_file", return_value="0" * 64):
                        self.assertEqual(_raw_data_candidates(root, [path]), [relative])
                    other = next(
                        value for value in REVIEWED_CAMERA_SCREENSHOT_SHA256.values()
                        if value != expected
                    )
                    with patch("plategauge.gate_d_audit.sha256_file", return_value=other):
                        self.assertEqual(_raw_data_candidates(root, [path]), [relative])

    def test_real_hashing_rejects_one_byte_change_to_a_synthetic_fixture(self) -> None:
        relative = "reports/media/camera-home-2026-09-23.png"
        original = b"synthetic screenshot-fixture bytes only"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(original)
            with patch(
                "plategauge.gate_d_audit.REVIEWED_CAMERA_SCREENSHOT_SHA256",
                {relative: hashlib.sha256(original).hexdigest()},
            ):
                self.assertEqual(_raw_data_candidates(root, [path]), [])
                path.write_bytes(original + b"!")
                self.assertEqual(_raw_data_candidates(root, [path]), [relative])

    def test_renamed_unknown_and_lookalike_paths_stay_forbidden_even_with_matching_bytes(self) -> None:
        forbidden = [
            "reports/media/camera-home-2026-09-23-copy.png",
            "reports/media/camera-home-2026-09-23.PNG",
            "reports/media/camera-home-2026-09-23.png.jpg",
            "reports/media/camera-home-2026-09-23.png/other.png",
            "reports/media/camera-home-2026-09-24.png",
            "reports/media/camera-h\u043eme-2026-09-23.png",  # Cyrillic letter, not ASCII o.
            "reports/media/unreviewed.png",
            "data/raw/camera-home-2026-09-23.png",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / relative for relative in forbidden]
            with patch(
                "plategauge.gate_d_audit.sha256_file",
                return_value=REVIEWED_CAMERA_SCREENSHOT_SHA256[
                    "reports/media/camera-home-2026-09-23.png"
                ],
            ) as digest:
                self.assertEqual(_raw_data_candidates(root, paths), sorted(forbidden))
                digest.assert_not_called()

    def test_missing_unreadable_or_symlinked_reviewed_file_is_not_accepted(self) -> None:
        relative = "reports/media/camera-idle-2026-09-23.png"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / relative
            self.assertEqual(_raw_data_candidates(root, [path]), [relative])
            with patch("plategauge.gate_d_audit.sha256_file", side_effect=PermissionError):
                self.assertEqual(_raw_data_candidates(root, [path]), [relative])
            with (
                patch.object(Path, "is_symlink", return_value=True),
                patch("plategauge.gate_d_audit.sha256_file") as digest,
            ):
                self.assertEqual(_raw_data_candidates(root, [path]), [relative])
                digest.assert_not_called()

    def test_raw_archives_and_workbooks_remain_forbidden_in_media_directory(self) -> None:
        forbidden = [
            f"reports/media/camera-home-2026-09-23{suffix}"
            for suffix in (".7z", ".rar", ".tar", ".tgz", ".xls", ".xlsx", ".zip")
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                _raw_data_candidates(root, [root / relative for relative in forbidden]),
                sorted(forbidden),
            )

    def test_historical_allowlist_is_unchanged_and_does_not_depend_on_new_hashes(self) -> None:
        historical = [
            "reports/media/01-question-and-boundary.png",
            "reports/media/02-frozen-results.png",
            "reports/media/03-selected-success.png",
            "reports/media/04-largest-failure.png",
            "reports/media/05-category-shift-method.png",
            "reports/media/06-limits-and-attribution.png",
            "reports/media/plategauge-social-preview-1280x640.png",
            "web/public/examples/synthetic-placeholder.jpg",
            "web/tests/fixtures/preprocess-golden/synthetic-placeholder.png",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("plategauge.gate_d_audit.sha256_file") as digest:
                self.assertEqual(
                    _raw_data_candidates(root, [root / relative for relative in historical]), []
                )
                digest.assert_not_called()


class GateDAuditTests(unittest.TestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_local_candidate_is_technically_clean_but_not_release_authorized(self) -> None:
        report = audit_gate_d_candidate(self.repo_root)
        self.assertEqual(report["technicalStatus"], "passed")
        self.assertEqual(report["releaseReadiness"], "blocked_pending_gate_d_actions")
        self.assertEqual(report["failedChecks"], [])
        self.assertIn("gate_d_approval", report["pendingChecks"])
        self.assertIn("source_commit", report["pendingChecks"])
        by_id = {check["id"]: check for check in report["checks"]}
        self.assertEqual(by_id["static_bundle_allowlist"]["status"], "pass")
        self.assertEqual(by_id["web_benchmark_evidence_binding"]["status"], "pass")
        self.assertEqual(by_id["web_benchmark_evidence_binding"]["evidence"]["exampleCount"], 10)
        self.assertEqual(by_id["raw_data_boundary"]["status"], "pass")
        self.assertTrue(by_id["raw_data_boundary"]["evidence"]["localRawDirectoryIgnored"])
        self.assertEqual(by_id["secret_and_host_path_scan"]["status"], "pass")
        self.assertEqual(by_id["public_smoke_fail_closed"]["status"], "pass")
        self.assertEqual(by_id["candidate_version_consistency"]["status"], "pass")
        self.assertNotIn("final_manifest_version", report["pendingChecks"])


if __name__ == "__main__":
    unittest.main()
