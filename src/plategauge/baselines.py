"""Leakage-safe numerical baselines without a scikit-learn dependency."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .metrics import macro_category_mae
from .schema import ManifestRecord

PAIRING_MAP_FIELDS = (
    "sample_id",
    "original_after_path",
    "wrong_after_path",
    "source_sample_id",
    "rule",
    "scope",
)


@dataclass(slots=True)
class RidgeRegressor:
    """Standardized closed-form Ridge with an unpenalized intercept."""

    alpha: float = 1.0
    clip: tuple[float, float] | None = (0.0, 1.0)
    feature_mean_: np.ndarray | None = None
    feature_scale_: np.ndarray | None = None
    coefficients_: np.ndarray | None = None
    intercept_: float | None = None

    def fit(self, features: np.ndarray, targets: np.ndarray) -> RidgeRegressor:
        x = np.asarray(features, dtype=np.float64)
        y = np.asarray(targets, dtype=np.float64).reshape(-1)
        if x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or len(y) == 0:
            raise ValueError("Ridge fit requires non-empty X[n,p] and y[n]")
        if self.alpha < 0 or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Ridge inputs and alpha must be finite, with alpha >= 0")
        self.feature_mean_ = x.mean(axis=0)
        scale = x.std(axis=0)
        self.feature_scale_ = np.where(scale > 1e-12, scale, 1.0)
        standardized = (x - self.feature_mean_) / self.feature_scale_
        self.intercept_ = float(y.mean())
        centered_y = y - self.intercept_
        sample_count, feature_count = standardized.shape
        if feature_count > sample_count:
            # The dual form is algebraically equivalent for Ridge but avoids a
            # prohibitively large p-by-p solve for the 1,536-D DINO pair features.
            gram = standardized @ standardized.T
            regularized = gram + self.alpha * np.eye(sample_count, dtype=np.float64)
            try:
                dual = np.linalg.solve(regularized, centered_y)
            except np.linalg.LinAlgError:
                dual = np.linalg.pinv(regularized) @ centered_y
            self.coefficients_ = standardized.T @ dual
        else:
            gram = standardized.T @ standardized
            regularized = gram + self.alpha * np.eye(feature_count, dtype=np.float64)
            right_hand_side = standardized.T @ centered_y
            try:
                self.coefficients_ = np.linalg.solve(regularized, right_hand_side)
            except np.linalg.LinAlgError:
                self.coefficients_ = np.linalg.pinv(regularized) @ right_hand_side
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        if (
            self.feature_mean_ is None
            or self.feature_scale_ is None
            or self.coefficients_ is None
            or self.intercept_ is None
        ):
            raise RuntimeError("RidgeRegressor must be fit before predict")
        feature_mean = self.feature_mean_
        feature_scale = self.feature_scale_
        coefficients = self.coefficients_
        intercept = self.intercept_
        x = np.asarray(features, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != len(coefficients):
            raise ValueError("Prediction feature shape does not match fitted model")
        predictions = ((x - feature_mean) / feature_scale) @ coefficients + intercept
        if self.clip is not None:
            predictions = np.clip(predictions, self.clip[0], self.clip[1])
        return np.asarray(predictions, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class RidgeSelection:
    alpha: float
    mean_macro_mae: float
    scores: dict[str, float]


def select_ridge_alpha(
    features: np.ndarray,
    targets: np.ndarray,
    categories: np.ndarray,
    validation_folds: np.ndarray,
    *,
    alphas: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0),
) -> RidgeSelection:
    """Select alpha only within supplied development folds.

    A smaller alpha wins exact ties. The caller must pass inner-fold identifiers,
    never outer-test membership selected after seeing outcomes.
    """

    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    category_array = np.asarray(categories, dtype=str)
    folds = np.asarray(validation_folds)
    if not (len(x) == len(y) == len(category_array) == len(folds)):
        raise ValueError("All Ridge selection arrays must have equal length")
    unique_folds = np.unique(folds)
    if len(unique_folds) < 2:
        raise ValueError("At least two inner folds are required")
    scores: dict[str, float] = {}
    for alpha in sorted(alphas):
        fold_scores: list[float] = []
        for fold in unique_folds:
            validation = folds == fold
            training = ~validation
            model = RidgeRegressor(alpha=alpha).fit(x[training], y[training])
            predictions = model.predict(x[validation])
            fold_scores.append(macro_category_mae(y[validation], predictions, category_array[validation]))
        scores[format(alpha, "g")] = float(np.mean(fold_scores))
    best_alpha = min(sorted(alphas), key=lambda alpha: (scores[format(alpha, "g")], alpha))
    return RidgeSelection(
        alpha=best_alpha,
        mean_macro_mae=scores[format(best_alpha, "g")],
        scores=scores,
    )


def training_median_baseline(train_targets: np.ndarray, size: int) -> np.ndarray:
    """Predict only the development-fold median for each held-out example."""

    y = np.asarray(train_targets, dtype=np.float64)
    if y.size == 0 or size < 0:
        raise ValueError("Median baseline requires training targets and size >= 0")
    return np.full(size, float(np.median(y)), dtype=np.float64)


def observer_leftover_reference(scores: np.ndarray) -> np.ndarray:
    """Map the published 1--7 consumed-level convention to leftover fraction.

    The LeFood paper evaluates observer levels as ``score / 7`` against the
    normalized amount consumed. PlateGauge's target is amount remaining, so
    this contextual (non-model) reference is ``1 - score / 7``. The compressed
    endpoint is retained to reproduce the paper's stated convention rather
    than silently inventing an alternative scale.
    """

    values = np.asarray(scores, dtype=np.float64)
    if values.size == 0 or not np.isfinite(values).all() or np.any((values < 1) | (values > 7)):
        raise ValueError("Observer scores must be finite values in [1, 7]")
    return 1.0 - values / 7.0


@dataclass(frozen=True, slots=True)
class WrongPairControl:
    after_path_by_sample: dict[str, str]
    source_sample_by_sample: dict[str, str]
    rule_by_sample: dict[str, str]
    singleton_categories: tuple[str, ...]

    @property
    def excluded_singleton_categories(self) -> tuple[str, ...]:
        """Compatibility alias: the approved bijective control excludes no rows."""

        return ()


def fixed_within_category_wrong_pairs(records: list[ManifestRecord]) -> WrongPairControl:
    """Create a deterministic, same-fold, bijective wrong-pair control.

    Non-singleton categories use a stable cyclic derangement. A singleton starts
    with its own after image, then swaps that assignment with the preimage of the
    first stable donor after image from a non-singleton category in the same
    outer fold. Thus every before image receives a different after image, every
    after image is used exactly once, and no evaluation fold is crossed.
    """

    by_category: dict[str, list[ManifestRecord]] = defaultdict(list)
    for record in records:
        if record.is_valid:
            by_category[record.category].append(record)
    valid = sorted((record for record in records if record.is_valid), key=lambda row: row.sample_id)
    by_id = {record.sample_id: record for record in valid}
    if len(by_id) != len(valid):
        raise ValueError("Wrong-pair control requires unique sample IDs")
    assignment: dict[str, str] = {}
    rules: dict[str, str] = {}
    singletons: list[ManifestRecord] = []
    for _category, category_records in sorted(by_category.items()):
        ordered = sorted(category_records, key=lambda record: record.sample_id)
        if len(ordered) < 2:
            singleton = ordered[0]
            singletons.append(singleton)
            assignment[singleton.sample_id] = singleton.sample_id
            continue
        for index, record in enumerate(ordered):
            assignment[record.sample_id] = ordered[(index + 1) % len(ordered)].sample_id
            rules[record.sample_id] = "within_category_cyclic"

    used_donor_owners: set[str] = set()
    for singleton in sorted(singletons, key=lambda record: record.sample_id):
        category_size = {
            category: len(category_records) for category, category_records in by_category.items()
        }
        donors = [
            record
            for record in valid
            if record.outer_fold == singleton.outer_fold
            and record.category != singleton.category
            and category_size[record.category] >= 2
            and record.sample_id not in used_donor_owners
        ]
        if not donors:
            raise ValueError(
                f"Singleton {singleton.sample_id!r} has no same-fold non-singleton donor"
            )
        donor_owner = donors[0]
        preimages = [
            sample_id
            for sample_id, assigned_owner in assignment.items()
            if assigned_owner == donor_owner.sample_id
        ]
        if len(preimages) != 1 or preimages[0] == singleton.sample_id:
            raise ValueError("Wrong-pair donor does not have one stable preimage")
        preimage = preimages[0]
        assignment[singleton.sample_id], assignment[preimage] = (
            assignment[preimage],
            assignment[singleton.sample_id],
        )
        rules[singleton.sample_id] = "same_fold_singleton_swap"
        rules[preimage] = "same_fold_singleton_swap_donor_preimage"
        used_donor_owners.add(donor_owner.sample_id)

    if set(assignment) != set(by_id) or set(assignment.values()) != set(by_id):
        raise ValueError("Wrong-pair assignments must be a complete bijection")
    if any(sample_id == source_id for sample_id, source_id in assignment.items()):
        raise ValueError("Wrong-pair assignments must not contain self-pairs")
    if any(
        by_id[sample_id].outer_fold != by_id[source_id].outer_fold
        for sample_id, source_id in assignment.items()
    ):
        raise ValueError("Wrong-pair assignments must remain within each outer fold")
    return WrongPairControl(
        after_path_by_sample={
            sample_id: by_id[source_id].after_path for sample_id, source_id in assignment.items()
        },
        source_sample_by_sample=assignment,
        rule_by_sample=rules,
        singleton_categories=tuple(sorted(record.category for record in singletons)),
    )
