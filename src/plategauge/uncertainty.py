"""Empirical interval correction, release gate, and abstention utilities."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np

from .metrics import macro_category_mae, target_slice_labels

QuantileStrategy = Literal["legacy_numpy_higher_v1", "finite_rank_v2"]
LEGACY_QUANTILE_STRATEGY: QuantileStrategy = "legacy_numpy_higher_v1"
FINITE_RANK_QUANTILE_STRATEGY: QuantileStrategy = "finite_rank_v2"


def ordered_quantiles_numpy(raw: np.ndarray) -> np.ndarray:
    """Map unconstrained triples to q05 <= q50 <= q95 within [0, 1]."""

    values = np.asarray(raw, dtype=np.float64)
    if values.ndim == 0 or values.size == 0 or values.shape[-1] != 3 or not np.isfinite(values).all():
        raise ValueError("Raw quantile values must be finite with final dimension 3")
    sigmoid = 1.0 / (1.0 + np.exp(-np.clip(values, -60.0, 60.0)))
    median = sigmoid[..., 1]
    lower = median * sigmoid[..., 0]
    upper = median + (1.0 - median) * sigmoid[..., 2]
    return np.stack((lower, median, upper), axis=-1)


def pinball_loss_numpy(targets: np.ndarray, predictions: np.ndarray, quantile: float) -> float:
    if not 0.0 < quantile < 1.0:
        raise ValueError("quantile must lie strictly inside (0, 1)")
    y = np.asarray(targets, dtype=np.float64)
    prediction = np.asarray(predictions, dtype=np.float64)
    residual = y - prediction
    return float(np.mean(np.maximum(quantile * residual, (quantile - 1.0) * residual)))


def finite_sample_quantile(
    values: np.ndarray,
    *,
    coverage: float = 0.90,
    strategy: QuantileStrategy = LEGACY_QUANTILE_STRATEGY,
) -> float:
    """Return an explicitly versioned empirical residual quantile.

    The default preserves the frozen NumPy-higher recipe exactly. It can pick
    one order statistic above the finite-sample rank. The opt-in v2 strategy
    selects rank ceil((n + 1) * coverage), clipped to n, directly. Neither
    strategy establishes coverage under category or acquisition shift.
    """

    scores = np.asarray(values, dtype=np.float64).reshape(-1)
    if scores.size == 0 or not np.isfinite(scores).all() or not 0.0 < coverage < 1.0:
        raise ValueError("Invalid empirical quantile inputs")
    if strategy not in (LEGACY_QUANTILE_STRATEGY, FINITE_RANK_QUANTILE_STRATEGY):
        raise ValueError("Unknown empirical quantile strategy")
    if strategy == FINITE_RANK_QUANTILE_STRATEGY:
        index = min(len(scores), math.ceil((len(scores) + 1) * coverage)) - 1
        return float(np.partition(scores, index)[index])
    probability = min(1.0, math.ceil((len(scores) + 1) * coverage) / len(scores))
    return float(np.quantile(scores, probability, method="higher"))


def interval_correction(
    targets: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    *,
    coverage: float = 0.90,
    strategy: QuantileStrategy = LEGACY_QUANTILE_STRATEGY,
) -> float:
    """Calculate a symmetric correction; frozen callers retain the legacy recipe."""

    y = np.asarray(targets, dtype=np.float64).reshape(-1)
    low = np.asarray(lower, dtype=np.float64).reshape(-1)
    high = np.asarray(upper, dtype=np.float64).reshape(-1)
    if not (len(y) == len(low) == len(high)) or np.any(low > high):
        raise ValueError("Interval calibration arrays must align and be ordered")
    scores = np.maximum.reduce((low - y, y - high, np.zeros_like(y)))
    return finite_sample_quantile(scores, coverage=coverage, strategy=strategy)


def _validated_intervals(
    lower: np.ndarray, upper: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    low = np.asarray(lower)
    high = np.asarray(upper)
    if (
        low.size == 0
        or low.shape != high.shape
        or not np.isfinite(low).all()
        or not np.isfinite(high).all()
        or np.any(low > high)
    ):
        raise ValueError("Intervals must be non-empty, finite, equal-shaped and ordered")
    return low, high


def _interval_widths(lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    low, high = _validated_intervals(lower, upper)
    # Finite endpoints alone do not prevent subtraction from overflowing.
    with np.errstate(over="ignore", invalid="ignore"):
        widths: np.ndarray = high - low
    if not np.isfinite(widths).all() or np.any(widths < 0):
        raise ValueError("Interval widths must be finite and non-negative")
    return widths


def correct_intervals(
    lower: np.ndarray, upper: np.ndarray, correction: float
) -> tuple[np.ndarray, np.ndarray]:
    if correction < 0 or not math.isfinite(correction):
        raise ValueError("correction must be finite and non-negative")
    low, high = _validated_intervals(
        np.asarray(lower, dtype=np.float64), np.asarray(upper, dtype=np.float64)
    )
    return np.clip(low - correction, 0.0, 1.0), np.clip(high + correction, 0.0, 1.0)


def derive_abstention_threshold(
    corrected_lower: np.ndarray,
    corrected_upper: np.ndarray,
    *,
    maximum_width: float = 0.30,
    retention_quantile: float = 0.80,
) -> float:
    if not math.isfinite(maximum_width) or not 0.0 <= maximum_width <= 1.0:
        raise ValueError("maximum_width must be finite and in [0, 1]")
    if not math.isfinite(retention_quantile) or not 0.0 <= retention_quantile <= 1.0:
        raise ValueError("retention_quantile must be finite and in [0, 1]")
    widths = _interval_widths(corrected_lower, corrected_upper)
    return min(maximum_width, float(np.quantile(widths, retention_quantile, method="higher")))


def retention_mask(
    corrected_lower: np.ndarray, corrected_upper: np.ndarray, threshold: float
) -> np.ndarray:
    if threshold < 0 or not math.isfinite(threshold):
        raise ValueError("Abstention threshold must be finite and non-negative")
    widths = _interval_widths(corrected_lower, corrected_upper)
    retained: np.ndarray = widths <= threshold + 1e-12
    return retained


@dataclass(frozen=True, slots=True)
class IntervalGate:
    passed: bool
    aggregate_coverage: float
    mean_width: float
    minimum_broad_slice_coverage: float
    slice_coverage: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_interval_gate(
    targets: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> IntervalGate:
    """Apply the frozen 85-95%/0.30/80%-per-slice public interval gate."""

    y = np.asarray(targets, dtype=np.float64).reshape(-1)
    low = np.asarray(lower, dtype=np.float64).reshape(-1)
    high = np.asarray(upper, dtype=np.float64).reshape(-1)
    if not (len(y) == len(low) == len(high)) or len(y) == 0 or np.any(low > high):
        raise ValueError("Invalid interval gate inputs")
    low, high = _validated_intervals(low, high)
    covered = (y >= low) & (y <= high)
    labels = target_slice_labels(y)
    slice_coverage = {
        label: float(np.mean(covered[labels == label])) for label in sorted(np.unique(labels))
    }
    aggregate = float(np.mean(covered))
    mean_width = float(np.mean(high - low))
    minimum = min(slice_coverage.values())
    passed = 0.85 <= aggregate <= 0.95 and mean_width <= 0.30 and minimum >= 0.80
    return IntervalGate(passed, aggregate, mean_width, minimum, slice_coverage)


@dataclass(frozen=True, slots=True)
class AbstentionGate:
    passed: bool
    retention: float
    error_reduction: float
    minimum_broad_slice_retention: float
    retained_macro_category_mae: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_abstention_gate(
    targets: np.ndarray,
    predictions: np.ndarray,
    categories: np.ndarray,
    retained: np.ndarray,
) -> AbstentionGate:
    """Apply the preregistered usefulness gate for an approximately-80% policy."""

    y = np.asarray(targets, dtype=np.float64)
    prediction = np.asarray(predictions, dtype=np.float64)
    category_array = np.asarray(categories, dtype=str)
    keep = np.asarray(retained, dtype=bool)
    if not (len(y) == len(prediction) == len(category_array) == len(keep)) or not np.any(keep):
        raise ValueError("Invalid abstention gate inputs")
    full_error = macro_category_mae(y, prediction, category_array)
    retained_error = macro_category_mae(y[keep], prediction[keep], category_array[keep])
    reduction = (full_error - retained_error) / full_error if full_error > 0 else 0.0
    labels = target_slice_labels(y)
    slice_retention = [float(np.mean(keep[labels == label])) for label in np.unique(labels)]
    minimum = min(slice_retention)
    overall = float(np.mean(keep))
    return AbstentionGate(
        passed=reduction >= 0.20 and minimum >= 0.50,
        retention=overall,
        error_reduction=reduction,
        minimum_broad_slice_retention=minimum,
        retained_macro_category_mae=retained_error,
    )
