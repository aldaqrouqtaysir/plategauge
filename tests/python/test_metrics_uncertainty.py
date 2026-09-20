from __future__ import annotations

import unittest

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
    correct_intervals,
    derive_abstention_threshold,
    evaluate_abstention_gate,
    evaluate_interval_gate,
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


if __name__ == "__main__":
    unittest.main()
