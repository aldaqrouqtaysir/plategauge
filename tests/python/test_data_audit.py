from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from PIL import Image

from plategauge.data import (
    audit_manifest,
    build_lefood_manifest,
    create_and_audit_lefood_artifacts,
    sha256_file,
)
from plategauge.folds import EXPECTED_VALID_COUNTS

HEADER = (
    "ID",
    "Name of the food",
    "Image Before Eaten",
    "Weight Before Eaten (g)",
    "Image After Eaten",
    "Weight After Eaten (g)",
    "Visual Estimation by Observer (1-7)",
)


def make_synthetic_lefood(root: Path) -> None:
    image_root = root / "leftover dataset"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    dataset_id = 1

    def add_matched(category: str, after_mass: int) -> None:
        nonlocal dataset_id
        before_name = f"{category}_{dataset_id:03d}_DSC_{dataset_id:04d}_bef.JPG"
        after_name = f"{category}_{dataset_id:03d}_DSC_{dataset_id + 1000:04d}_aft.JPG"
        sheet.append((dataset_id, f"Food {category}", before_name, 100, after_name, after_mass, 4))
        for role, filename, color in (
            ("data_before", before_name, (dataset_id % 251, 20, 30)),
            ("data_after", after_name, (10, dataset_id % 251, 40)),
        ):
            directory = image_root / role / category
            directory.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (8, 8), color).save(directory / filename)
        dataset_id += 1

    for category, count in EXPECTED_VALID_COUNTS.items():
        for _ in range(count):
            add_matched(category, 50)
    for _ in range(10):
        add_matched("000", 101)
    for _missing_index in range(154):
        category = "000"
        sheet.append(
            (
                dataset_id,
                "Missing",
                f"{category}_{dataset_id:03d}_missing_bef.JPG",
                100,
                f"{category}_{dataset_id:03d}_missing_aft.JPG",
                50,
                4,
            )
        )
        dataset_id += 1
    workbook.save(root / "data_original.xlsx")


class LeFoodAuditTests(unittest.TestCase):
    def test_strict_builder_and_audit_reproduce_expected_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_synthetic_lefood(root)
            records, source_rows, diagnostics = build_lefood_manifest(
                root, detect_near_duplicates=False
            )
            self.assertEqual(len(records), 524)
            self.assertEqual(sum(record.is_valid for record in records), 514)
            self.assertEqual(sum(not record.is_valid for record in records), 10)
            self.assertEqual(sum(row["status"] == "missing_image" for row in source_rows), 154)
            self.assertEqual(diagnostics["near_duplicate_edges"], 0)
            report = audit_manifest(
                records,
                dataset_root=root,
                workbook_rows=len(source_rows),
                missing_image_rows=154,
                verify_hashes=True,
            )
            self.assertTrue(report.passed, report.issues)
            self.assertTrue(report.hashes_verified)
            unverified = audit_manifest(records)
            self.assertFalse(unverified.passed)
            self.assertIn("not verified", "; ".join(unverified.issues))

    def test_artifact_writer_and_hash_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            root = temporary / "raw"
            root.mkdir()
            make_synthetic_lefood(root)
            manifest = temporary / "manifest.csv"
            source = temporary / "source.csv"
            report_path = temporary / "audit.json"
            duplicate_review = temporary / "duplicates.csv"
            report = create_and_audit_lefood_artifacts(
                root,
                manifest_path=manifest,
                source_audit_path=source,
                report_path=report_path,
                duplicate_review_path=duplicate_review,
                detect_near_duplicates=False,
            )
            self.assertTrue(report.passed)
            audit_payload = json.loads(report_path.read_text())
            self.assertEqual(audit_payload["valid_pairs"], 514)
            self.assertEqual(audit_payload["manifest_sha256"], sha256_file(manifest))
            self.assertEqual(len(source.read_text(encoding="utf-8").splitlines()), 679)
            self.assertEqual(len(duplicate_review.read_text(encoding="utf-8").splitlines()), 1)

            first = root / report_path.parent.name  # deliberately not a manifest image
            self.assertFalse(first.exists())
            records, _, _ = build_lefood_manifest(root, detect_near_duplicates=False)
            image = root / records[0].before_path
            image.write_bytes(b"tampered")
            failed = audit_manifest(records, dataset_root=root, verify_hashes=True)
            self.assertFalse(failed.passed)
            self.assertTrue(any("Hash mismatch" in issue for issue in failed.issues))


if __name__ == "__main__":
    unittest.main()
