from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from plategauge.errors import DataIntegrityError
from plategauge.release_bundle_audit import audit_release_bundle


class ReleaseBundleAuditTests(unittest.TestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_current_production_bundle_passes(self) -> None:
        report = audit_release_bundle(self.repo_root, self.repo_root / "web/dist")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["examples"]["count"], 20)
        self.assertEqual(report["fileCount"], 35)
        self.assertEqual(report["benchmarkEvidence"]["workloadRecordCount"], 8)
        self.assertEqual(report["benchmarkEvidence"]["categoryRecordCount"], 34)
        self.assertEqual(report["remoteRuntimeResources"], [])
        self.assertEqual(report["sourceMaps"], 0)

    def test_unexpected_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "dist"
            shutil.copytree(self.repo_root / "web/dist", bundle)
            (bundle / "source-data.csv").write_text("raw", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "forbidden files"):
                audit_release_bundle(self.repo_root, bundle)

    def test_model_substitution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "dist"
            shutil.copytree(self.repo_root / "web/dist", bundle)
            model = bundle / "models/plategauge.onnx"
            model.write_bytes(model.read_bytes() + b"tamper")
            with self.assertRaisesRegex(DataIntegrityError, "ONNX bytes differ"):
                audit_release_bundle(self.repo_root, bundle)

    def test_retired_disclosure_asset_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "dist"
            shutil.copytree(self.repo_root / "web/dist", bundle)
            (bundle / "legal/AI_ASSISTANCE_LOG.md").write_text(
                "retired synthetic fixture", encoding="utf-8"
            )
            with self.assertRaisesRegex(DataIntegrityError, "allowlist mismatch"):
                audit_release_bundle(self.repo_root, bundle)

    def test_benchmark_evidence_substitution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "dist"
            shutil.copytree(self.repo_root / "web/dist", bundle)
            evidence = bundle / "evidence" / "benchmark-evidence.json"
            evidence.write_bytes(evidence.read_bytes() + b"\n")
            with self.assertRaisesRegex(DataIntegrityError, "benchmark evidence bytes differ"):
                audit_release_bundle(self.repo_root, bundle)

    def test_stale_pre_release_language_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "dist"
            shutil.copytree(self.repo_root / "web/dist", bundle)
            index = bundle / "index.html"
            index.write_text(
                index.read_text(encoding="utf-8") + "\n<!-- not released -->\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DataIntegrityError, "pre-release status language"):
                audit_release_bundle(self.repo_root, bundle)

    def test_meta_csp_does_not_claim_unsupported_anti_framing(self) -> None:
        index = (self.repo_root / "web/index.html").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy", index)
        self.assertIn("object-src 'none'", index)
        self.assertNotIn("frame-ancestors", index)


if __name__ == "__main__":
    unittest.main()
