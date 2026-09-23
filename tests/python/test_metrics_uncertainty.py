from __future__ import annotations

import math
import unittest
from typing import cast

import numpy as np

from plategauge.metrics import (
    category_bootstrap_mae_difference,
    holm_adjust,
    macro_category_mae,
    metrics_by_slice,
    paired_sign_flip_pvalue,
    regression_metrics,
    target_slice_labels,
)
from plategauge.uncertainty import (
    FINITE_RANK_QUANTILE_STRATEGY,
    LEGACY_QUANTILE_STRATEGY,
    QuantileStrategy,
    correct_intervals,
    derive_abstention_threshold,
    evaluate_abstention_gate,
    evaluate_interval_gate,
    finite_sample_quantile,
    interval_correction,
    ordered_quantiles_numpy,
    retention_mask,
)


class MetricTests(unittest.TestCase):
    def setUp(self) -> None:
        self.y = np.asarray([0.0, 0.2, 0.5, 1.0])
        self.prediction = np.asarray([0.1, 0.1, 0.4, 0.8])
        self.categories = np.asarray(["a", "a", "b", "b"])

    def test_regression_summary(self) -> None:
        summary = regression_metrics(self.y, self.prediction, self.categories)
        self.assertAlmostEqual(summary.micro_mae, 0.125)
        self.assertAlmostEqual(summary.macro_category_mae, 0.125)
        self.assertEqual(summary.n, 4)

    def test_macro_weights_categories_not_rows(self) -> None:
        y = np.asarray([0.0, 0.0, 0.0, 1.0])
        prediction = np.asarray([0.0, 0.0, 0.0, 0.0])
        categories = np.asarray(["large", "large", "large", "small"])
        self.assertAlmostEqual(macro_category_mae(y, prediction, categories), 0.5)

    def test_bootstrap_is_deterministic_and_paired(self) -> None:
        a = category_bootstrap_mae_difference(
            self.y, self.prediction, np.zeros(4), self.categories, replicates=200, seed=7
        )
        b = category_bootstrap_mae_difference(
            self.y, self.prediction, np.zeros(4), self.categories, replicates=200, seed=7
        )
        self.assertEqual(a, b)

    def test_holm_preserves_input_order(self) -> None:
        adjusted = holm_adjust([0.04, 0.01, 0.03])
        self.assertEqual(adjusted, [0.06, 0.03, 0.06])

    def test_target_slices_include_boundaries(self) -> None:
        labels = target_slice_labels(np.asarray([0.0, 0.25, 0.5, 0.75, 0.8, 1.0]))
        self.assertEqual(labels.tolist(), ["zero", "(0,.25]", "(.25,.50]", "(.50,.75]", "(.75,1)", "one"])

    def test_slice_metrics_and_sign_flip(self) -> None:
        labels = np.asarray(["low", "low", "high", "high"])
        result = metrics_by_slice(self.y, self.prediction, self.categories, labels)
        self.assertEqual(set(result), {"high", "low"})
        pvalue = paired_sign_flip_pvalue(np.asarray([-0.1, -0.2, -0.1]), replicates=100, seed=1)
        self.assertGreaterEqual(pvalue, 0.0)
        self.assertLessEqual(pvalue, 1.0)

    def test_invalid_metric_inputs_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            regression_metrics([], [], [])
        with self.assertRaisesRegex(ValueError, "p-values"):
            holm_adjust([1.1])


class UncertaintyTests(unittest.TestCase):
    def test_default_quantile_preserves_frozen_numpy_higher_recipe(self) -> None:
        generator = np.random.default_rng(20260919)
        for count in (1, 2, 5, 20, 34, 411, 412):
            scores = generator.uniform(0.0, 1.0, size=count)
            for coverage in (0.01, 0.5, 0.9, 0.99):
                with self.subTest(count=count, coverage=coverage):
                    probability = min(1.0, math.ceil((count + 1) * coverage) / count)
                    expected = float(np.quantile(scores, probability, method="higher"))
                    self.assertEqual(finite_sample_quantile(scores, coverage=coverage), expected)
                    self.assertEqual(
                        finite_sample_quantile(
                            scores, coverage=coverage, strategy=LEGACY_QUANTILE_STRATEGY
                        ),
                        expected,
                    )
                    rank = min(count, math.ceil((count + 1) * coverage))
                    self.assertEqual(
                        finite_sample_quantile(
                            scores, coverage=coverage, strategy=FINITE_RANK_QUANTILE_STRATEGY
                        ),
                        float(np.sort(scores)[rank - 1]),
                    )

    def test_finite_rank_v2_is_explicit_and_selects_the_one_based_rank(self) -> None:
        scores = np.arange(20, dtype=np.float64)
        self.assertEqual(finite_sample_quantile(scores), 19.0)
        self.assertEqual(
            finite_sample_quantile(scores, strategy=FINITE_RANK_QUANTILE_STRATEGY), 18.0
        )
        self.assertEqual(scores.tolist(), list(range(20)))
        for values, coverage, expected in (
            ([0.4], 0.9, 0.4),
            ([0.1, 0.3], 0.01, 0.1),
            ([0.1, 0.3], 0.99, 0.3),
            ([0.2] * 20, 0.9, 0.2),
        ):
            with self.subTest(values=values, coverage=coverage):
                self.assertEqual(
                    finite_sample_quantile(
                        np.asarray(values),
                        coverage=coverage,
                        strategy=FINITE_RANK_QUANTILE_STRATEGY,
                    ),
                    expected,
                )

    def test_interval_correction_does_not_opt_in_to_v2_implicitly(self) -> None:
        y = np.arange(20, dtype=np.float64) / 20.0
        zeros = np.zeros_like(y)
        self.assertEqual(interval_correction(y, zeros, zeros), 0.95)
        self.assertEqual(
            interval_correction(y, zeros, zeros, strategy=FINITE_RANK_QUANTILE_STRATEGY),
            0.9,
        )

    def test_quantile_rejects_invalid_parameters(self) -> None:
        for values in (np.asarray([]), np.asarray([np.nan]), np.asarray([np.inf])):
            with self.subTest(values=values), self.assertRaises(ValueError):
                finite_sample_quantile(values)
        for coverage in (0.0, 1.0, -0.1, np.nan, np.inf):
            with self.subTest(coverage=coverage), self.assertRaises(ValueError):
                finite_sample_quantile(np.asarray([0.1]), coverage=coverage)
        with self.assertRaisesRegex(ValueError, "strategy"):
            finite_sample_quantile(np.asarray([0.1]), strategy=cast(QuantileStrategy, "unknown"))

    def test_ordered_mapping_is_bounded(self) -> None:
        output = ordered_quantiles_numpy(np.asarray([[100.0, -1.0, -100.0], [0.0, 0.0, 0.0]]))
        self.assertTrue(np.all(output >= 0.0))
        self.assertTrue(np.all(output <= 1.0))
        self.assertTrue(np.all(output[:, 0] <= output[:, 1]))
        self.assertTrue(np.all(output[:, 1] <= output[:, 2]))

    def test_calibration_correction_and_threshold(self) -> None:
        y = np.asarray([0.1, 0.3, 0.5, 0.7, 0.9])
        low = y - 0.04
        high = y + 0.04
        correction = interval_correction(y, low, high)
        corrected_low, corrected_high = correct_intervals(low, high, correction)
        threshold = derive_abstention_threshold(corrected_low, corrected_high)
        self.assertEqual(correction, 0.0)
        self.assertLessEqual(threshold, 0.30)
        self.assertTrue(retention_mask(corrected_low, corrected_high, threshold).all())

    def test_interval_gate_passes_good_empirical_intervals(self) -> None:
        y = np.linspace(0.0, 1.0, 20)
        low = np.clip(y - 0.1, 0.0, 1.0)
        high = np.clip(y + 0.1, 0.0, 1.0)
        # Force exactly two misses while retaining every broad slice above 80%.
        low[[5, 10]] = y[[5, 10]] + 0.01
        high[[5, 10]] = y[[5, 10]] + 0.02
        gate = evaluate_interval_gate(y, low, high)
        self.assertAlmostEqual(gate.aggregate_coverage, 0.9)
        self.assertTrue(gate.passed)

    def test_abstention_gate_reports_reduction(self) -> None:
        y = np.asarray([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
        prediction = y.copy()
        prediction[[1, 6]] += 0.5
        categories = np.asarray(["a", "a", "b", "b", "c", "c", "d", "d"])
        retained = np.asarray([True, False, True, True, True, True, False, True])
        gate = evaluate_abstention_gate(y, prediction, categories, retained)
        self.assertGreaterEqual(gate.error_reduction, 0.2)

    def test_invalid_interval_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ordered"):
            correct_intervals(np.asarray([0.8]), np.asarray([0.2]), 0.0)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            retention_mask(np.asarray([0.1]), np.asarray([0.2]), -1.0)

    def test_interval_helpers_reject_nonfinite_empty_and_broadcast_shapes(self) -> None:
        invalid_pairs = (
            (np.asarray([np.nan]), np.asarray([0.9])),
            (np.asarray([0.1]), np.asarray([np.inf])),
            (np.asarray([]), np.asarray([])),
            (np.zeros((2, 1)), np.full(2, 0.1)),
            (np.asarray([0.8]), np.asarray([0.2])),
        )
        for low, high in invalid_pairs:
            with self.subTest(low=low, high=high):
                with self.assertRaises(ValueError):
                    correct_intervals(low, high, 0.0)
                with self.assertRaises(ValueError):
                    derive_abstention_threshold(low, high)
                with self.assertRaises(ValueError):
                    retention_mask(low, high, 0.3)
        with self.assertRaises(ValueError):
            evaluate_interval_gate(np.asarray([0.1]), np.asarray([np.nan]), np.asarray([0.2]))
        for raw in (np.asarray(1.0), np.empty((0, 3)), np.asarray([[0.0, np.nan, 1.0]])):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                ordered_quantiles_numpy(raw)

    def test_threshold_parameters_are_validated(self) -> None:
        low, high = np.asarray([0.0]), np.asarray([0.1])
        for invalid in (-0.1, 1.1, np.nan, np.inf):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "maximum_width"):
                    derive_abstention_threshold(low, high, maximum_width=invalid)
                with self.assertRaisesRegex(ValueError, "retention_quantile"):
                    derive_abstention_threshold(low, high, retention_quantile=invalid)
        self.assertEqual(derive_abstention_threshold(low, high, maximum_width=0.0), 0.0)

    def test_valid_interval_helpers_preserve_legacy_dtype_arithmetic(self) -> None:
        for dtype in (np.float32, np.float64):
            with self.subTest(dtype=dtype):
                low = np.asarray([0.1, 0.2, 0.3], dtype=dtype)
                high = np.asarray([0.2, 0.5, 0.8], dtype=dtype)
                widths = high - low
                expected = min(0.3, float(np.quantile(widths, 0.8, method="higher")))
                self.assertEqual(derive_abstention_threshold(low, high), expected)
                np.testing.assert_array_equal(
                    retention_mask(low, high, expected), widths <= expected + 1e-12
                )

    def test_finite_endpoints_cannot_hide_overflowed_widths(self) -> None:
        for dtype in (np.float32, np.float64):
            high = np.asarray([np.finfo(dtype).max], dtype=dtype)
            low = -high
            with self.subTest(dtype=dtype), np.errstate(over="raise", invalid="raise"):
                with self.assertRaisesRegex(ValueError, "widths must be finite"):
                    derive_abstention_threshold(low, high)
                with self.assertRaisesRegex(ValueError, "widths must be finite"):
                    retention_mask(low, high, 0.3)


if __name__ == "__main__":
    unittest.main()
