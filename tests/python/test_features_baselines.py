from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
from PIL import Image

from plategauge.baselines import (
    RidgeRegressor,
    fixed_within_category_wrong_pairs,
    observer_leftover_reference,
    select_ridge_alpha,
    training_median_baseline,
)
from plategauge.features import (
    extract_feature_matrix,
    extract_handcrafted_features,
    handcrafted_feature_names,
)
from plategauge.folds import fold_for_category
from plategauge.schema import ManifestRecord


def _record(sample_id: str, category: str, after_path: str) -> ManifestRecord:
    return ManifestRecord(
        sample_id=sample_id,
        source_row=2,
        food_name="test",
        category=category,
        before_path=f"before/{sample_id}.jpg",
        after_path=after_path,
        before_mass_g=100.0,
        after_mass_g=50.0,
        leftover_fraction=0.5,
        observer_score=4,
        before_width=224,
        before_height=224,
        after_width=224,
        after_height=224,
        before_sha256="a" * 64,
        after_sha256="b" * 64,
        outer_fold=fold_for_category(category),
    )


class FeatureTests(unittest.TestCase):
    def test_feature_vector_is_finite_and_named(self) -> None:
        before = np.zeros((40, 50, 3), dtype=np.uint8)
        after = before.copy()
        after[10:30, 10:40, 0] = 255
        features = extract_handcrafted_features(before, after)
        self.assertEqual(features.shape, (len(handcrafted_feature_names()),))
        self.assertTrue(np.isfinite(features).all())
        self.assertLess(features[handcrafted_feature_names().index("ssim")], 1.0)

    def test_identical_images_have_one_ssim_and_zero_hist_change(self) -> None:
        image = Image.new("RGB", (20, 20), (50, 100, 150))
        features = extract_handcrafted_features(image, image)
        names = handcrafted_feature_names()
        self.assertAlmostEqual(features[names.index("ssim")], 1.0)
        self.assertTrue(np.allclose(features[:96], 0.0))

    def test_empty_feature_matrix_has_stable_width(self) -> None:
        matrix = extract_feature_matrix([])
        self.assertEqual(matrix.shape, (0, len(handcrafted_feature_names())))


class RidgeTests(unittest.TestCase):
    def test_ridge_learns_simple_relationship(self) -> None:
        x = np.arange(30, dtype=np.float64).reshape(-1, 1) / 30.0
        y = 0.2 + 0.5 * x[:, 0]
        model = RidgeRegressor(alpha=0.0, clip=None).fit(x, y)
        self.assertLess(float(np.max(np.abs(model.predict(x) - y))), 1e-10)

    def test_ridge_selection_uses_all_inner_folds(self) -> None:
        x = np.column_stack((np.arange(16), np.arange(16) ** 2)).astype(float)
        y = np.linspace(0.0, 1.0, 16)
        categories = np.asarray([f"{index // 4:03d}" for index in range(16)])
        folds = np.repeat(np.arange(4), 4)
        result = select_ridge_alpha(x, y, categories, folds, alphas=(0.1, 1.0))
        self.assertIn(result.alpha, {0.1, 1.0})
        self.assertEqual(set(result.scores), {"0.1", "1"})

    def test_dual_solution_matches_equivalent_primal_ridge_solution(self) -> None:
        generator = np.random.default_rng(20260919)
        x = generator.normal(size=(7, 13))
        y = generator.normal(size=7)
        alpha = 0.7
        model = RidgeRegressor(alpha=alpha, clip=None).fit(x, y)

        mean = x.mean(axis=0)
        scale = np.where(x.std(axis=0) > 1e-12, x.std(axis=0), 1.0)
        standardized = (x - mean) / scale
        centered = y - y.mean()
        expected = np.linalg.solve(
            standardized.T @ standardized + alpha * np.eye(x.shape[1]),
            standardized.T @ centered,
        )
        self.assertTrue(np.allclose(model.coefficients_, expected, rtol=1e-10, atol=1e-10))
        expected_predictions = standardized @ expected + y.mean()
        self.assertTrue(
            np.allclose(model.predict(x), expected_predictions, rtol=1e-10, atol=1e-10)
        )

    def test_dual_singular_solve_uses_pseudoinverse_fallback(self) -> None:
        x = np.arange(18, dtype=np.float64).reshape(3, 6)
        y = np.asarray([0.1, 0.5, 0.9])
        original_solve = np.linalg.solve
        with mock.patch(
            "plategauge.baselines.np.linalg.solve",
            side_effect=np.linalg.LinAlgError("synthetic singular system"),
        ):
            model = RidgeRegressor(alpha=0.0, clip=None).fit(x, y)
        self.assertIsNotNone(model.coefficients_)
        self.assertTrue(np.isfinite(model.predict(x)).all())
        # Keep the local binding alive so static analysis confirms the patch
        # affects only the fitted call, not NumPy globally.
        self.assertIs(np.linalg.solve, original_solve)

    def test_median_baseline_never_uses_test_targets(self) -> None:
        predictions = training_median_baseline(np.asarray([0.1, 0.2, 0.9]), 2)
        self.assertTrue(np.allclose(predictions, [0.2, 0.2]))

    def test_ridge_rejects_unfitted_or_invalid_inputs(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "fit"):
            RidgeRegressor().predict(np.zeros((1, 1)))
        with self.assertRaisesRegex(ValueError, "non-empty"):
            RidgeRegressor().fit(np.empty((0, 1)), np.empty(0))
        with self.assertRaisesRegex(ValueError, "shape"):
            RidgeRegressor().fit(np.ones((2, 1)), np.ones(2)).predict(np.ones((2, 2)))

    def test_selection_requires_multiple_folds(self) -> None:
        with self.assertRaisesRegex(ValueError, "two inner folds"):
            select_ridge_alpha(
                np.ones((2, 1)),
                np.ones(2),
                np.asarray(["a", "a"]),
                np.zeros(2),
            )


class ContextualControlTests(unittest.TestCase):
    def test_observer_mapping_reproduces_published_consumed_scale(self) -> None:
        values = observer_leftover_reference(np.asarray([1, 7]))
        self.assertTrue(np.allclose(values, [6 / 7, 0]))
        with self.assertRaisesRegex(ValueError, r"\[1, 7\]"):
            observer_leftover_reference(np.asarray([0]))

    def test_wrong_pairs_are_bijective_with_same_fold_singleton_swap(self) -> None:
        records = [
            _record("b", "006", "after/b.jpg"),
            _record("a", "006", "after/a.jpg"),
            _record("singleton", "003", "after/singleton.jpg"),
        ]
        control = fixed_within_category_wrong_pairs(records)
        self.assertEqual(
            control.after_path_by_sample,
            {
                "a": "after/b.jpg",
                "b": "after/singleton.jpg",
                "singleton": "after/a.jpg",
            },
        )
        self.assertEqual(set(control.source_sample_by_sample), {"a", "b", "singleton"})
        self.assertEqual(set(control.source_sample_by_sample.values()), {"a", "b", "singleton"})
        self.assertEqual(control.singleton_categories, ("003",))
        self.assertEqual(control.excluded_singleton_categories, ())


if __name__ == "__main__":
    unittest.main()
