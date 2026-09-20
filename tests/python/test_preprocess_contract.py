from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plategauge.errors import DataIntegrityError
from plategauge.preprocess_contract import (
    expected_golden_payload,
    generate_preprocess_golden,
    preprocess_geometry,
    verify_preprocess_golden,
)


class PreprocessContractTests(unittest.TestCase):
    def test_geometry_matches_frozen_rounding_and_crop(self) -> None:
        self.assertEqual(
            preprocess_geometry(640, 480),
            {
                "source_width": 640,
                "source_height": 480,
                "resized_width": 341,
                "resized_height": 256,
                "crop_left": 58,
                "crop_top": 16,
                "crop_width": 224,
                "crop_height": 224,
            },
        )
        self.assertEqual(preprocess_geometry(513, 512)["resized_width"], 256)
        self.assertEqual(preprocess_geometry(515, 512)["resized_width"], 258)
        with self.assertRaises(ValueError):
            preprocess_geometry(0, 100)

    def test_generation_is_deterministic_and_verification_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = generate_preprocess_golden(root)
            second = generate_preprocess_golden(root)
            self.assertEqual(first, second)
            self.assertEqual(verify_preprocess_golden(root), first)
            self.assertEqual(len(first["fixtures"]), 3)
            source = root / first["fixtures"][0]["source_file"]
            source.write_bytes(source.read_bytes() + b"tamper")
            with self.assertRaisesRegex(DataIntegrityError, "hash mismatch"):
                verify_preprocess_golden(root)
            with self.assertRaisesRegex(DataIntegrityError, "differs"):
                generate_preprocess_golden(root)

    def test_checked_in_browser_fixtures_match_python(self) -> None:
        payload = verify_preprocess_golden("web/tests/fixtures/preprocess-golden")
        expected, _ = expected_golden_payload()
        self.assertEqual(payload, expected)
        for fixture in payload["fixtures"]:
            self.assertEqual(fixture["expected_rgba_bytes"], 224 * 224 * 4)
            self.assertEqual(fixture["expected_tensor_float_count"], 3 * 224 * 224)


if __name__ == "__main__":
    unittest.main()
