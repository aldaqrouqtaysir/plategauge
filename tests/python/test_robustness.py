from __future__ import annotations

import unittest

from PIL import Image, ImageChops

from plategauge.robustness import FROZEN_PERTURBATIONS, perturb_pair, same_image_pair, swapped_pair


class RobustnessTests(unittest.TestCase):
    def test_all_frozen_perturbations_execute(self) -> None:
        before = Image.new("RGB", (100, 80), (20, 30, 40))
        after = Image.new("RGB", (100, 80), (50, 60, 70))
        for perturbation in FROZEN_PERTURBATIONS:
            perturbed_before, perturbed_after = perturb_pair(before, after, perturbation)
            self.assertEqual(perturbed_before.size, before.size)
            self.assertEqual(perturbed_after.size, after.size)

    def test_misuse_pairs_are_deterministic(self) -> None:
        before = Image.new("RGB", (20, 20), (0, 0, 0))
        after = Image.new("RGB", (20, 20), (255, 255, 255))
        swapped_before, swapped_after = swapped_pair(before, after)
        self.assertIsNone(ImageChops.difference(swapped_before, after).getbbox())
        self.assertIsNone(ImageChops.difference(swapped_after, before).getbbox())
        same_before, same_after = same_image_pair(before)
        self.assertIsNone(ImageChops.difference(same_before, same_after).getbbox())


if __name__ == "__main__":
    unittest.main()
