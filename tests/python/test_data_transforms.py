from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from plategauge.data import _windowed_ssim, find_duplicate_groups, sha256_file
from plategauge.transforms import (
    PairedAugmentationConfig,
    PairedTrainTransform,
    deterministic_preprocess,
)


class DataUtilityTests(unittest.TestCase):
    def test_sha256_and_exact_duplicate_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.png"
            second = root / "b.png"
            third = root / "c.png"
            Image.new("RGB", (32, 32), (10, 20, 30)).save(first)
            Image.new("RGB", (32, 32), (10, 20, 30)).save(second)
            Image.new("RGB", (32, 32), (200, 30, 80)).save(third)
            self.assertEqual(sha256_file(first), sha256_file(second))
            assignments, exact, near_edges, candidates = find_duplicate_groups(
                [first, second, third]
            )
            self.assertEqual(exact, 1)
            self.assertEqual(assignments[first.as_posix()], assignments[second.as_posix()])
            self.assertNotIn(third.as_posix(), assignments)
            self.assertGreaterEqual(len(candidates), 1)
            self.assertGreaterEqual(near_edges, 0)

    def test_near_duplicate_requires_local_ssim_confirmation(self) -> None:
        left = np.zeros((64, 64), dtype=np.float64)
        right = left.copy()
        right[0, 0] = 1.0
        self.assertEqual(_windowed_ssim(left, left), 1.0)
        self.assertLess(_windowed_ssim(left, right), 1.0)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "a.png", root / "b.png"
            image = Image.new("RGB", (32, 32), (10, 10, 10))
            image.save(first, compress_level=0)
            image.save(second, compress_level=9)
            assignments, exact, near_edges, candidates = find_duplicate_groups([first, second])
            self.assertEqual(exact, 0)
            self.assertEqual(near_edges, 1)
            self.assertEqual(candidates[0]["match_type"], "phash_ssim")
            self.assertEqual(len(set(assignments.values())), 1)


class TransformTests(unittest.TestCase):
    def test_deterministic_preprocessing_contract(self) -> None:
        image = Image.new("RGB", (400, 300), (10, 20, 30))
        array = deterministic_preprocess(image)
        self.assertEqual(array.shape, (3, 224, 224))
        self.assertEqual(array.dtype, np.float32)
        self.assertTrue(np.isfinite(array).all())

    def test_pair_geometry_is_synchronized(self) -> None:
        image = Image.new("RGB", (300, 300), (0, 0, 0))
        for x in range(50, 150):
            for y in range(80, 180):
                image.putpixel((x, y), (255, 50, 10))
        config = PairedAugmentationConfig(brightness_jitter=0.0, contrast_jitter=0.0)
        transform = PairedTrainTransform(config, seed=42)
        before, after = transform(image, image)
        self.assertTrue(np.array_equal(before, after))

    def test_no_vertical_flip_is_configured(self) -> None:
        config = PairedAugmentationConfig()
        self.assertFalse(hasattr(config, "vertical_flip_probability"))

    def test_invalid_image_array_is_rejected(self) -> None:
        from plategauge.features import extract_handcrafted_features

        with self.assertRaisesRegex(ValueError, "HxWx3"):
            extract_handcrafted_features(np.zeros((4, 4)), np.zeros((4, 4)))


if __name__ == "__main__":
    unittest.main()
