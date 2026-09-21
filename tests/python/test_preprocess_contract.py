from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image

from plategauge.errors import DataIntegrityError
from plategauge.preprocess_contract import (
    expected_golden_payload,
    generate_preprocess_golden,
    preprocess_geometry,
    verify_preprocess_golden,
)
from plategauge.release_artifacts import canonical_json_sha256


class PreprocessContractTests(unittest.TestCase):
    def test_lossless_reencoding_is_portable_but_changed_pixels_fail(self) -> None:
        def reencode(image: Image.Image) -> bytes:
            buffer = BytesIO()
            image.save(buffer, format="PNG", compress_level=0)
            return buffer.getvalue()

        with mock.patch("plategauge.preprocess_contract._png_bytes", side_effect=reencode):
            expected, _ = expected_golden_payload()
            stored = verify_preprocess_golden("web/tests/fixtures/preprocess-golden")
            self.assertNotEqual(
                expected["fixtures"][0]["source_sha256"],
                stored["fixtures"][0]["source_sha256"],
            )
            self.test_checked_in_browser_fixtures_match_python()

        def corrupt_pixels(image: Image.Image) -> bytes:
            modified = image.copy()
            modified.putpixel((128, 128), (255, 0, 0))
            return reencode(modified)

        with (
            mock.patch("plategauge.preprocess_contract._png_bytes", side_effect=corrupt_pixels),
            self.assertRaises(AssertionError),
        ):
            self.test_checked_in_browser_fixtures_match_python()

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
        expected, regenerated_sources = expected_golden_payload()
        # Pillow/zlib builds may losslessly encode identical pixels differently.
        # verify_preprocess_golden above still checks the committed PNG hashes,
        # every decoded RGBA/tensor hash, and the manifest's evidence digest.
        for stored, regenerated in zip(payload["fixtures"], expected["fixtures"], strict=True):
            source = Path("web/tests/fixtures/preprocess-golden") / stored["source_file"]
            with (
                Image.open(source) as committed_image,
                Image.open(BytesIO(regenerated_sources[stored["source_file"]])) as new_image,
            ):
                self.assertEqual(committed_image.size, new_image.size)
                self.assertEqual(
                    committed_image.convert("RGB").tobytes(),
                    new_image.convert("RGB").tobytes(),
                )
            regenerated["source_sha256"] = stored["source_sha256"]
        expected["evidence_sha256"] = canonical_json_sha256(
            {key: value for key, value in expected.items() if key != "evidence_sha256"}
        )
        self.assertEqual(payload, expected)
        for fixture in payload["fixtures"]:
            self.assertEqual(fixture["expected_rgba_bytes"], 224 * 224 * 4)
            self.assertEqual(fixture["expected_tensor_float_count"], 3 * 224 * 224)


if __name__ == "__main__":
    unittest.main()
