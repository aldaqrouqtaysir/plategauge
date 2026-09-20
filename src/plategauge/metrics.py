"""Frozen evaluation metrics and category-level statistical comparisons."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


def _vectors(
    targets: np.ndarray | list[float], predictions: np.ndarray | list[float]
) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(targets, dtype=np.float64).reshape(-1)
    prediction = np.asarray(predictions, dtype=np.float64).reshape(-1)
    if y.size == 0 or len(y) != len(prediction):
        raise ValueError("Metrics require non-empty equal-length vectors")
    if not np.isfinite(y).all() or not np.isfinite(prediction).all():
        raise ValueError("Metric inputs must be finite")
    return y, prediction


def macro_category_mae(
    targets: np.ndarray | list[float],
    predictions: np.ndarray | list[float],
    categories: np.ndarray | list[str],
) -> float:
    """Average per-category MAE, weighting each category equally."""

    y, prediction = _vectors(targets, predictions)
    category_array = np.asarray(categories, dtype=str).reshape(-1)
    if len(category_array) != len(y):
        raise ValueError("categories must align with metric vectors")
    return float(
        np.mean(
            [
                np.mean(np.abs(y[category_array == category] - prediction[category_array == category]))
                for category in np.unique(category_array)
            ]
        )
    )


def _rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0 + 1.0
        start = end
    return ranks


def spearman_correlation(targets: np.ndarray, predictions: np.ndarray) -> float:
    y, prediction = _vectors(targets, predictions)
    y_rank, prediction_rank = _rankdata(y), _rankdata(prediction)
    if np.std(y_rank) == 0 or np.std(prediction_rank) == 0:
        return float("nan")
    return float(np.corrcoef(y_rank, prediction_rank)[0, 1])


@dataclass(frozen=True, slots=True)
class MetricSummary:
    n: int
    category_count: int
    macro_category_mae: float
    micro_mae: float
    rmse: float
    signed_bias: float
    median_absolute_error: float
    p90_absolute_error: float
    spearman: float | None
    within_0_10: float
    within_0_20: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def regression_metrics(
    targets: np.ndarray | list[float],
    predictions: np.ndarray | list[float],
    categories: np.ndarray | list[str],
) -> MetricSummary:
    y, prediction = _vectors(targets, predictions)
    category_array = np.asarray(categories, dtype=str).reshape(-1)
    if len(category_array) != len(y):
        raise ValueError("categories must align with metric vectors")
    errors = prediction - y
    absolute = np.abs(errors)
    spearman = spearman_correlation(y, prediction)
    return MetricSummary(
        n=len(y),
        category_count=len(np.unique(category_array)),
        macro_category_mae=macro_category_mae(y, prediction, category_array),
        micro_mae=float(absolute.mean()),
        rmse=float(np.sqrt(np.mean(errors**2))),
        signed_bias=float(errors.mean()),
        median_absolute_error=float(np.median(absolute)),
        p90_absolute_error=float(np.quantile(absolute, 0.90)),
        spearman=None if math.isnan(spearman) else spearman,
        within_0_10=float(np.mean(absolute <= 0.10)),
        within_0_20=float(np.mean(absolute <= 0.20)),
    )


def target_slice_labels(targets: np.ndarray | list[float]) -> np.ndarray:
    """Return the six preregistered leftover-range labels."""

    y = np.asarray(targets, dtype=np.float64).reshape(-1)
    labels = np.full(len(y), None, dtype=object)
    labels[y == 0.0] = "zero"
    labels[(y > 0.0) & (y <= 0.25)] = "(0,.25]"
    labels[(y > 0.25) & (y <= 0.50)] = "(.25,.50]"
    labels[(y > 0.50) & (y <= 0.75)] = "(.50,.75]"
    labels[(y > 0.75) & (y < 1.0)] = "(.75,1)"
    labels[y == 1.0] = "one"
    if any(value is None for value in labels):
        raise ValueError("Targets for slices must lie in [0, 1]")
    return labels.astype(str)


def metrics_by_slice(
    targets: np.ndarray,
    predictions: np.ndarray,
    categories: np.ndarray,
    slice_labels: np.ndarray,
) -> dict[str, dict[str, Any]]:
    """Compute the same summary for every non-empty supplied slice."""

    y, prediction = _vectors(targets, predictions)
    category_array = np.asarray(categories, dtype=str)
    labels = np.asarray(slice_labels, dtype=str)
    if not (len(y) == len(category_array) == len(labels)):
        raise ValueError("Slice arrays must align")
    result: dict[str, dict[str, Any]] = {}
    for label in sorted(np.unique(labels)):
        mask = labels == label
        result[label] = regression_metrics(y[mask], prediction[mask], category_array[mask]).to_dict()
    return result


@dataclass(frozen=True, slots=True)
class BootstrapDifference:
    metric: str
    estimate_a_minus_b: float
    lower_95: float
    upper_95: float
    replicates: int
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def category_bootstrap_mae_difference(
    targets: np.ndarray,
    predictions_a: np.ndarray,
    predictions_b: np.ndarray,
    categories: np.ndarray,
    *,
    replicates: int = 10_000,
    seed: int = 20260919,
) -> BootstrapDifference:
    """Paired bootstrap of macro-category MAE differences.

    Negative values favor model A. Sampling category means with replacement is
    equivalent to preserving every observation in each sampled category.
    """

    y, a = _vectors(targets, predictions_a)
    _, b = _vectors(targets, predictions_b)
    category_array = np.asarray(categories, dtype=str)
    if len(category_array) != len(y) or replicates < 1:
        raise ValueError("Invalid category bootstrap inputs")
    unique = np.unique(category_array)
    per_category = np.asarray(
        [
            np.mean(np.abs(a[category_array == category] - y[category_array == category]))
            - np.mean(np.abs(b[category_array == category] - y[category_array == category]))
            for category in unique
        ],
        dtype=np.float64,
    )
    estimate = float(per_category.mean())
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(unique), size=(replicates, len(unique)))
    differences = per_category[samples].mean(axis=1)
    lower, upper = np.quantile(differences, [0.025, 0.975])
    return BootstrapDifference(
        metric="macro_category_mae",
        estimate_a_minus_b=estimate,
        lower_95=float(lower),
        upper_95=float(upper),
        replicates=replicates,
        seed=seed,
    )


def paired_sign_flip_pvalue(
    per_category_differences: np.ndarray,
    *,
    replicates: int = 100_000,
    seed: int = 20260919,
) -> float:
    """Two-sided Monte Carlo paired sign-flip test with plus-one correction."""

    differences = np.asarray(per_category_differences, dtype=np.float64).reshape(-1)
    if len(differences) == 0 or replicates < 1 or not np.isfinite(differences).all():
        raise ValueError("Sign-flip test requires finite category differences")
    observed = abs(float(differences.mean()))
    rng = np.random.default_rng(seed)
    extreme = 0
    chunk = 10_000
    completed = 0
    while completed < replicates:
        size = min(chunk, replicates - completed)
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=(size, len(differences)))
        permuted = np.abs((signs * differences).mean(axis=1))
        extreme += int(np.sum(permuted >= observed - 1e-15))
        completed += size
    return (extreme + 1.0) / (replicates + 1.0)


def holm_adjust(pvalues: list[float]) -> list[float]:
    """Holm family-wise error adjustment in original input order."""

    if any(not 0.0 <= value <= 1.0 for value in pvalues):
        raise ValueError("p-values must lie in [0, 1]")
    count = len(pvalues)
    order = sorted(range(count), key=pvalues.__getitem__)
    adjusted = [0.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (count - rank) * pvalues[index]))
        adjusted[index] = running
    return adjusted
