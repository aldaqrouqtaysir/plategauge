"""Frozen category-disjoint evaluation folds.

These assignments are part of the preregistered evaluation protocol. They must not
be regenerated after examining model performance.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping

from .errors import DataIntegrityError

FROZEN_CATEGORY_FOLDS: dict[int, tuple[str, ...]] = {
    0: ("001", "005", "019", "022", "032"),
    1: ("002", "008", "010", "014"),
    2: ("009", "011", "012", "016", "025", "028", "029", "033"),
    3: ("003", "006", "013", "015", "017", "021", "026", "031"),
    4: ("000", "004", "007", "018", "020", "023", "024", "027", "030"),
}

EXPECTED_VALID_COUNTS: dict[str, int] = {
    "000": 1,
    "001": 78,
    "002": 76,
    "003": 1,
    "004": 17,
    "005": 2,
    "006": 2,
    "007": 17,
    "008": 4,
    "009": 21,
    "010": 9,
    "011": 18,
    "012": 16,
    "013": 22,
    "014": 14,
    "015": 20,
    "016": 5,
    "017": 5,
    "018": 4,
    "019": 14,
    "020": 6,
    "021": 12,
    "022": 6,
    "023": 22,
    "024": 21,
    "025": 1,
    "026": 19,
    "027": 3,
    "028": 5,
    "029": 26,
    "030": 11,
    "031": 22,
    "032": 3,
    "033": 11,
}

EXPECTED_FOLD_COUNTS: dict[int, int] = {0: 103, 1: 103, 2: 103, 3: 103, 4: 102}

_CATEGORY_TO_FOLD = {
    category: fold for fold, categories in FROZEN_CATEGORY_FOLDS.items() for category in categories
}


def fold_for_category(category: str) -> int:
    """Return the frozen outer fold for a zero-padded category code."""

    try:
        return _CATEGORY_TO_FOLD[category]
    except KeyError as exc:
        raise DataIntegrityError(f"Category {category!r} is outside frozen folds") from exc


def validate_frozen_folds() -> None:
    """Validate uniqueness, coverage, and planned fold totals."""

    flattened = [category for categories in FROZEN_CATEGORY_FOLDS.values() for category in categories]
    if len(flattened) != 34 or len(set(flattened)) != 34:
        raise DataIntegrityError("Frozen folds must contain each of 34 categories exactly once")
    if set(flattened) != set(EXPECTED_VALID_COUNTS):
        raise DataIntegrityError("Frozen fold categories differ from expected dataset categories")
    totals = {
        fold: sum(EXPECTED_VALID_COUNTS[category] for category in categories)
        for fold, categories in FROZEN_CATEGORY_FOLDS.items()
    }
    if totals != EXPECTED_FOLD_COUNTS:
        raise DataIntegrityError(f"Frozen fold totals changed: {totals!r}")


def validate_observed_counts(categories: Iterable[str], *, exact: bool = True) -> dict[str, int]:
    """Check observed valid records against the preregistered category counts."""

    observed = dict(sorted(Counter(categories).items()))
    unknown = set(observed).difference(EXPECTED_VALID_COUNTS)
    if unknown:
        raise DataIntegrityError(f"Unknown categories in manifest: {sorted(unknown)!r}")
    if exact and observed != EXPECTED_VALID_COUNTS:
        missing = {
            category: expected - observed.get(category, 0)
            for category, expected in EXPECTED_VALID_COUNTS.items()
            if expected != observed.get(category, 0)
        }
        raise DataIntegrityError(f"Valid category counts do not match frozen protocol: {missing!r}")
    return observed


def validate_duplicate_groups(
    categories: Iterable[str], duplicate_groups: Iterable[str], folds: Iterable[int]
) -> None:
    """Ensure a confirmed duplicate component never crosses an outer fold."""

    seen: dict[str, set[int]] = defaultdict(set)
    for category, group, fold in zip(categories, duplicate_groups, folds, strict=True):
        expected = fold_for_category(category)
        if fold != expected:
            raise DataIntegrityError(
                f"Category {category} assigned to fold {fold}, expected frozen fold {expected}"
            )
        if group:
            seen[group].add(fold)
    crossing = {group: sorted(group_folds) for group, group_folds in seen.items() if len(group_folds) > 1}
    if crossing:
        raise DataIntegrityError(f"Duplicate groups cross folds: {crossing!r}")


def inner_folds(outer_fold: int) -> tuple[int, ...]:
    """Return the four development folds used as nested inner folds."""

    if outer_fold not in FROZEN_CATEGORY_FOLDS:
        raise DataIntegrityError(f"Invalid outer fold {outer_fold!r}")
    return tuple(fold for fold in sorted(FROZEN_CATEGORY_FOLDS) if fold != outer_fold)


def categories_by_fold() -> Mapping[int, tuple[str, ...]]:
    """Expose a read-only-by-convention copy for serialization."""

    return dict(FROZEN_CATEGORY_FOLDS)


validate_frozen_folds()
