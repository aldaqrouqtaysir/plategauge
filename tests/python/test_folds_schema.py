from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plategauge.errors import DataIntegrityError
from plategauge.folds import (
    EXPECTED_FOLD_COUNTS,
    EXPECTED_VALID_COUNTS,
    FROZEN_CATEGORY_FOLDS,
    fold_for_category,
    inner_folds,
    validate_duplicate_groups,
    validate_observed_counts,
)
from plategauge.schema import ManifestRecord, read_manifest, write_manifest


def record(**overrides: object) -> ManifestRecord:
    values: dict[str, object] = {
        "sample_id": "lefood-0001",
        "source_row": 2,
        "food_name": "Bubur",
        "category": "000",
        "before_path": "leftover dataset/data_before/000/a.JPG",
        "after_path": "leftover dataset/data_after/000/b.JPG",
        "before_mass_g": 100.0,
        "after_mass_g": 25.0,
        "leftover_fraction": 0.25,
        "observer_score": 4,
        "before_width": 640,
        "before_height": 480,
        "after_width": 640,
        "after_height": 480,
        "before_sha256": "a" * 64,
        "after_sha256": "b" * 64,
        "outer_fold": 4,
    }
    values.update(overrides)
    return ManifestRecord(**values)  # type: ignore[arg-type]


class FrozenFoldTests(unittest.TestCase):
    def test_fold_contract_has_34_categories_and_514_rows(self) -> None:
        categories = [value for fold in FROZEN_CATEGORY_FOLDS.values() for value in fold]
        self.assertEqual(len(categories), 34)
        self.assertEqual(len(set(categories)), 34)
        self.assertEqual(sum(EXPECTED_VALID_COUNTS.values()), 514)
        self.assertEqual(
            {
                fold: sum(EXPECTED_VALID_COUNTS[category] for category in fold_categories)
                for fold, fold_categories in FROZEN_CATEGORY_FOLDS.items()
            },
            EXPECTED_FOLD_COUNTS,
        )

    def test_observed_counts_and_inner_folds(self) -> None:
        observed = [
            category for category, count in EXPECTED_VALID_COUNTS.items() for _ in range(count)
        ]
        self.assertEqual(validate_observed_counts(observed), EXPECTED_VALID_COUNTS)
        self.assertEqual(inner_folds(2), (0, 1, 3, 4))
        self.assertEqual(fold_for_category("001"), 0)
        with self.assertRaisesRegex(DataIntegrityError, "outside frozen"):
            fold_for_category("999")
        with self.assertRaisesRegex(DataIntegrityError, "Invalid outer"):
            inner_folds(9)

    def test_observed_count_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(DataIntegrityError, "do not match"):
            validate_observed_counts(["000"], exact=True)
        self.assertEqual(validate_observed_counts(["000"], exact=False), {"000": 1})

    def test_cross_fold_duplicate_is_rejected(self) -> None:
        with self.assertRaisesRegex(DataIntegrityError, "cross folds"):
            validate_duplicate_groups(
                ["001", "002"], ["same", "same"], [fold_for_category("001"), fold_for_category("002")]
            )


class ManifestSchemaTests(unittest.TestCase):
    def test_round_trip_preserves_record(self) -> None:
        original = record()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.csv"
            write_manifest([original], path)
            self.assertEqual(read_manifest(path), [original])

    def test_target_must_equal_mass_ratio(self) -> None:
        with self.assertRaisesRegex(DataIntegrityError, "must equal"):
            record(leftover_fraction=0.24)

    def test_excluded_after_greater_than_before_is_preserved(self) -> None:
        excluded = record(
            before_mass_g=100.0,
            after_mass_g=102.0,
            leftover_fraction=1.02,
            is_valid=False,
            exclusion_reason="after_mass_exceeds_before_mass",
        )
        self.assertFalse(excluded.is_valid)

    def test_valid_target_outside_unit_interval_is_rejected(self) -> None:
        with self.assertRaisesRegex(DataIntegrityError, r"\[0, 1\]"):
            record(before_mass_g=100.0, after_mass_g=102.0, leftover_fraction=1.02)

    def test_path_escape_is_rejected(self) -> None:
        with self.assertRaisesRegex(DataIntegrityError, "safe dataset-relative"):
            record(before_path="../escape.jpg")

    def test_invalid_boolean_token_is_rejected(self) -> None:
        row = record().to_row()
        row["is_valid"] = "yes"
        with self.assertRaisesRegex(DataIntegrityError, "true.*false"):
            ManifestRecord.from_row(row)


if __name__ == "__main__":
    unittest.main()
