"""Read-only reproduction of the non-binding duplicate-safe fold proposal.

This module deliberately does not expose a writer.  It verifies the frozen data
gate inputs, derives category components from reviewed duplicate edges, and
solves the exact-capacity reassignment problem without changing the active
folds.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .data import sha256_file
from .errors import DataIntegrityError
from .folds import EXPECTED_FOLD_COUNTS, EXPECTED_VALID_COUNTS, fold_for_category
from .schema import MANIFEST_FIELDS, ManifestRecord

ADVISORY_STATUS = "NOT_ACTIVE_REQUIRES_APPROVAL"
FOLD_CAPACITIES = tuple(EXPECTED_FOLD_COUNTS[index] for index in range(5))
_COST_RADIX = 64
_STATE_RADIX = max(FOLD_CAPACITIES) + 1
_DUPLICATE_FIELDS = (
    "left_path",
    "right_path",
    "match_type",
    "phash_distance",
    "ssim",
    "duplicate_group",
)


@dataclass(frozen=True, slots=True)
class FrozenInputHashes:
    """Expected SHA-256 values for every binding input to the proposal."""

    manifest: str
    duplicate_candidates: str
    audit_report: str
    frozen_folds: str


PINNED_INPUT_HASHES = FrozenInputHashes(
    manifest="e124542954f6776bdb9b20552b8be083cfa1e4890521d1c1b325d87edc64ee1d",
    duplicate_candidates="2cab543ff6427d12586432f470f80b8ed9b1e8f1f136e365f3a98655ee04e58a",
    audit_report="ece427f6a891772453fa9745bb3e8ee37e31298b5e20e073957146255cce0526",
    frozen_folds="2604c650119ff823dfff29803a4ebe4b5fa475bd550f38a17c9892bb6f1d414e",
)


@dataclass(frozen=True, slots=True)
class _Component:
    categories: tuple[str, ...]
    size: int
    moved_records: tuple[int, ...]
    moved_categories: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _Solution:
    folds: tuple[int, ...]
    states_evaluated: int
    memoized_state_hits: int
    moved_records: int
    moved_categories: int


@dataclass(frozen=True, slots=True)
class _ProposalRecord:
    """Fold-relevant view of a hash-pinned preregistration manifest row."""

    sample_id: str
    category: str
    before_path: str
    after_path: str
    duplicate_group: str
    is_valid: bool
    outer_fold: int


class _UnionFind:
    def __init__(self, items: set[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        parent = self._parent[item]
        if parent != item:
            self._parent[item] = self.find(parent)
        return self._parent[item]

    def union(self, left: str, right: str) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            self._parent[max(root_left, root_right)] = min(root_left, root_right)


def _required_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise DataIntegrityError(f"Required frozen input is not a regular file: {relative}")
    return path


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataIntegrityError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise DataIntegrityError(f"{label} must be a JSON object")
    return value


def _verify_hash(path: Path, expected: str, label: str) -> str:
    actual = sha256_file(path)
    if actual != expected:
        raise DataIntegrityError(
            f"{label} SHA-256 differs from the pinned input: expected {expected}, found {actual}"
        )
    return actual


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataIntegrityError(f"{label} must be an integer")
    return value


def _read_proposal_manifest(path: Path) -> list[_ProposalRecord]:
    """Read historical rows while validating non-fold fields under the active schema.

    Once an approved amendment becomes active, ``ManifestRecord`` correctly rejects
    the former fold numbers.  The proposal reproducer still needs that hash-pinned
    historical assignment, so it validates every other field through
    ``ManifestRecord`` after substituting the active fold and retains only the
    historical fold in this private view.
    """

    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != MANIFEST_FIELDS:
                raise DataIntegrityError("Proposal manifest columns differ from the frozen schema")
            rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise DataIntegrityError("Proposal manifest cannot be read as UTF-8 CSV") from exc

    records: list[_ProposalRecord] = []
    sample_ids: set[str] = set()
    for row in rows:
        historical_fold = _require_int(int(row["outer_fold"]), "historical outer_fold")
        validation_row = dict(row)
        validation_row["outer_fold"] = str(fold_for_category(row["category"]))
        validated = ManifestRecord.from_row(validation_row)
        if validated.sample_id in sample_ids:
            raise DataIntegrityError("sample_id values must be unique")
        sample_ids.add(validated.sample_id)
        records.append(
            _ProposalRecord(
                sample_id=validated.sample_id,
                category=validated.category,
                before_path=validated.before_path,
                after_path=validated.after_path,
                duplicate_group=validated.duplicate_group,
                is_valid=validated.is_valid,
                outer_fold=historical_fold,
            )
        )
    return records


def _load_frozen_assignment(
    path: Path, records: list[_ProposalRecord]
) -> tuple[dict[str, int], dict[int, int], dict[str, int]]:
    document = _load_json_object(path, "Frozen-fold configuration")
    if set(document) != {"schema_version", "status", "folds"}:
        raise DataIntegrityError("Frozen-fold configuration fields changed")
    if document["schema_version"] != "1.0":
        raise DataIntegrityError("Unsupported frozen-fold schema")
    if document["status"] != "preregistered; duplicate-review gate unresolved":
        raise DataIntegrityError("Frozen-fold status no longer describes the unresolved gate")
    raw_folds = document["folds"]
    if not isinstance(raw_folds, dict) or set(raw_folds) != {str(index) for index in range(5)}:
        raise DataIntegrityError("Frozen-fold configuration must define folds 0 through 4")

    category_to_fold: dict[str, int] = {}
    fold_counts: dict[int, int] = {}
    for fold in range(5):
        entry = raw_folds[str(fold)]
        if not isinstance(entry, dict) or set(entry) != {"categories", "expected_n"}:
            raise DataIntegrityError(f"Frozen fold {fold} fields changed")
        categories = entry["categories"]
        if (
            not isinstance(categories, list)
            or not categories
            or any(not isinstance(category, str) for category in categories)
        ):
            raise DataIntegrityError(f"Frozen fold {fold} categories must be a non-empty list")
        expected_n = _require_int(entry["expected_n"], f"fold {fold} expected_n")
        if expected_n != FOLD_CAPACITIES[fold]:
            raise DataIntegrityError(f"Frozen fold {fold} capacity changed")
        fold_counts[fold] = expected_n
        for category in categories:
            if category in category_to_fold:
                raise DataIntegrityError(f"Category {category} occurs in multiple frozen folds")
            category_to_fold[category] = fold

    if set(category_to_fold) != set(EXPECTED_VALID_COUNTS):
        raise DataIntegrityError(
            "Frozen folds do not cover the expected 34 categories exactly once"
        )
    valid_records = [record for record in records if record.is_valid]
    observed = dict(sorted(Counter(record.category for record in valid_records).items()))
    if observed != EXPECTED_VALID_COUNTS or len(valid_records) != 514:
        raise DataIntegrityError("Manifest valid records differ from the frozen 514-pair counts")
    for record in valid_records:
        if category_to_fold[record.category] != record.outer_fold:
            raise DataIntegrityError(
                f"Manifest fold for category {record.category} conflicts with frozen folds"
            )
    observed_folds = dict(sorted(Counter(record.outer_fold for record in valid_records).items()))
    if observed_folds != fold_counts or fold_counts != EXPECTED_FOLD_COUNTS:
        raise DataIntegrityError("Manifest or configuration fold sizes changed")
    return category_to_fold, fold_counts, observed


def _load_duplicate_rows(
    path: Path, records: list[_ProposalRecord], category_to_fold: Mapping[str, int]
) -> tuple[list[dict[str, str]], dict[str, set[str]], int]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _DUPLICATE_FIELDS:
                raise DataIntegrityError(
                    "Duplicate-candidate columns differ from the frozen schema"
                )
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise DataIntegrityError("Duplicate-candidate file cannot be read as UTF-8 CSV") from exc
    if not rows:
        raise DataIntegrityError("Duplicate-candidate file must not be empty")

    valid_path_records: dict[str, list[_ProposalRecord]] = defaultdict(list)
    manifest_groups: set[str] = set()
    for record in records:
        if not record.is_valid:
            continue
        valid_path_records[record.before_path].append(record)
        valid_path_records[record.after_path].append(record)
        manifest_groups.update(group for group in record.duplicate_group.split("+") if group)

    group_paths: dict[str, set[str]] = defaultdict(set)
    group_categories: dict[str, set[str]] = defaultdict(set)
    path_groups: dict[str, set[str]] = defaultdict(set)
    group_edges: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        if set(row) != set(_DUPLICATE_FIELDS):
            raise DataIntegrityError(f"Duplicate-candidate row {row_number} fields changed")
        left, right = row["left_path"], row["right_path"]
        group = row["duplicate_group"]
        if not left or not right or left == right or not group:
            raise DataIntegrityError(f"Duplicate-candidate row {row_number} is incomplete")
        if row["match_type"] not in {"exact_sha256", "phash_ssim"}:
            raise DataIntegrityError(f"Duplicate-candidate row {row_number} has unknown match_type")
        try:
            distance = int(row["phash_distance"])
            similarity = float(row["ssim"])
        except ValueError as exc:
            raise DataIntegrityError(
                f"Duplicate-candidate row {row_number} has non-numeric review values"
            ) from exc
        if not math.isfinite(similarity) or not 0.995 <= similarity <= 1.0:
            raise DataIntegrityError(f"Duplicate-candidate row {row_number} fails the SSIM gate")
        if not 0 <= distance <= 4:
            raise DataIntegrityError(f"Duplicate-candidate row {row_number} fails the pHash gate")
        if row["match_type"] == "exact_sha256" and (distance != 0 or similarity != 1.0):
            raise DataIntegrityError(
                f"Duplicate-candidate row {row_number} has invalid exact metrics"
            )

        for image_path in (left, right):
            matched = valid_path_records.get(image_path, [])
            if len(matched) != 1:
                raise DataIntegrityError(
                    f"Duplicate path {image_path!r} must map to exactly one valid manifest record"
                )
            record = matched[0]
            if group not in record.duplicate_group.split("+"):
                raise DataIntegrityError(
                    f"Duplicate group {group!r} is absent from manifest record {record.sample_id}"
                )
            if path_groups[image_path] and group not in path_groups[image_path]:
                raise DataIntegrityError(f"Duplicate path {image_path!r} occurs in multiple groups")
            path_groups[image_path].add(group)
            group_paths[group].add(image_path)
            group_categories[group].add(record.category)
        group_edges[group].append((left, right))

    if set(group_paths) != manifest_groups:
        raise DataIntegrityError("Manifest and reviewed duplicate-group identifiers differ")
    for group, paths in group_paths.items():
        image_union = _UnionFind(paths)
        for left, right in group_edges[group]:
            image_union.union(left, right)
        if len({image_union.find(path) for path in paths}) != 1:
            raise DataIntegrityError(f"Duplicate group {group!r} is not connected")

    crossing_groups = sum(
        len({category_to_fold[category] for category in categories}) > 1
        for categories in group_categories.values()
    )
    return rows, group_categories, crossing_groups


def _validate_audit(
    path: Path,
    records: list[_ProposalRecord],
    duplicate_rows: list[dict[str, str]],
    group_categories: Mapping[str, set[str]],
    crossing_groups: int,
    fold_counts: Mapping[int, int],
) -> None:
    audit = _load_json_object(path, "Data audit report")
    expected_values: dict[str, object] = {
        "schema_version": "1.0",
        "workbook_rows": 678,
        "matched_pairs": len(records),
        "missing_image_rows": 154,
        "valid_pairs": sum(record.is_valid for record in records),
        "invalid_mass_pairs": sum(not record.is_valid for record in records),
        "valid_categories": len({record.category for record in records if record.is_valid}),
        "fold_counts": {str(fold): count for fold, count in fold_counts.items()},
        "exact_duplicate_components": sum(
            row["match_type"] == "exact_sha256" for row in duplicate_rows
        ),
        "near_duplicate_edges": sum(row["match_type"] == "phash_ssim" for row in duplicate_rows),
        "duplicate_components": len(group_categories),
        "cross_fold_duplicate_components": crossing_groups,
        "files_verified": True,
        "hashes_verified": True,
        "expected_counts_match": True,
        "passed": False,
    }
    if set(audit) != set(expected_values) | {"issues"}:
        raise DataIntegrityError("Data audit fields differ from the frozen schema")
    for key, expected in expected_values.items():
        if audit.get(key) != expected:
            raise DataIntegrityError(
                f"Data audit {key!r} is inconsistent: expected {expected!r}, found {audit.get(key)!r}"
            )
    issues = audit.get("issues")
    if (
        not isinstance(issues, list)
        or not issues
        or any(not isinstance(item, str) for item in issues)
    ):
        raise DataIntegrityError("Blocked data audit must contain a non-empty string issue list")


def _make_components(
    group_categories: Mapping[str, set[str]],
    category_to_fold: Mapping[str, int],
    category_counts: Mapping[str, int],
) -> tuple[list[_Component], list[tuple[str, ...]]]:
    union = _UnionFind(set(category_counts))
    for linked_categories in group_categories.values():
        ordered = sorted(linked_categories)
        for category in ordered[1:]:
            union.union(ordered[0], category)
    grouped: dict[str, list[str]] = defaultdict(list)
    for category in category_counts:
        grouped[union.find(category)].append(category)
    category_groups = [tuple(sorted(categories)) for categories in grouped.values()]
    linked = sorted(component for component in category_groups if len(component) > 1)

    components: list[_Component] = []
    for categories in category_groups:
        size = sum(category_counts[category] for category in categories)
        moved_records = tuple(
            sum(
                category_counts[category]
                for category in categories
                if category_to_fold[category] != fold
            )
            for fold in range(5)
        )
        moved_categories = tuple(
            sum(category_to_fold[category] != fold for category in categories) for fold in range(5)
        )
        components.append(_Component(categories, size, moved_records, moved_categories))
    components.sort(key=lambda component: (-component.size, component.categories))
    if sum(component.size for component in components) != 514:
        raise DataIntegrityError("Duplicate-induced category components do not retain 514 records")
    if sum(len(component.categories) for component in components) != 34:
        raise DataIntegrityError(
            "Duplicate-induced category components do not retain 34 categories"
        )
    if len(components) * 3 > 128:
        raise DataIntegrityError("Too many components for deterministic packed-path tie-breaking")
    return components, linked


def _decode_used(keys: NDArray[np.uint64]) -> tuple[NDArray[np.uint64], ...]:
    radix = np.uint64(_STATE_RADIX)
    return (
        keys // radix ** np.uint64(3),
        (keys // radix ** np.uint64(2)) % radix,
        (keys // radix) % radix,
        keys % radix,
    )


def _solve(components: list[_Component]) -> _Solution:
    keys = np.zeros(1, dtype=np.uint64)
    costs = np.zeros(1, dtype=np.uint32)
    path_high = np.zeros(1, dtype=np.uint64)
    path_low = np.zeros(1, dtype=np.uint64)
    state_weights = np.asarray(
        [_STATE_RADIX**3, _STATE_RADIX**2, _STATE_RADIX, 1, 0], dtype=np.uint64
    )
    states_evaluated = 1
    memoized_state_hits = 0
    assigned_total = 0

    for component in components:
        used = _decode_used(keys)
        used_fifth = assigned_total - sum(used, start=np.zeros_like(keys))
        next_keys: list[NDArray[np.uint64]] = []
        next_costs: list[NDArray[np.uint32]] = []
        next_high: list[NDArray[np.uint64]] = []
        next_low: list[NDArray[np.uint64]] = []
        for fold in range(5):
            fold_used = used[fold] if fold < 4 else used_fifth
            mask = fold_used + component.size <= FOLD_CAPACITIES[fold]
            if not bool(np.any(mask)):
                continue
            selected_low = path_low[mask]
            next_keys.append(keys[mask] + np.uint64(component.size) * state_weights[fold])
            increment = (
                component.moved_records[fold] * _COST_RADIX + component.moved_categories[fold]
            )
            next_costs.append(costs[mask] + np.uint32(increment))
            next_high.append((path_high[mask] << np.uint64(3)) | (selected_low >> np.uint64(61)))
            next_low.append((selected_low << np.uint64(3)) | np.uint64(fold))
        if not next_keys:
            raise DataIntegrityError("No exact-capacity fold assignment exists")

        candidate_keys = np.concatenate(next_keys)
        candidate_costs = np.concatenate(next_costs)
        candidate_high = np.concatenate(next_high)
        candidate_low = np.concatenate(next_low)
        transition_count = len(candidate_keys)
        order = np.lexsort((candidate_low, candidate_high, candidate_costs, candidate_keys))
        candidate_keys = candidate_keys[order]
        first = np.ones(transition_count, dtype=np.bool_)
        first[1:] = candidate_keys[1:] != candidate_keys[:-1]
        chosen = order[first]
        keys = candidate_keys[first]
        costs = candidate_costs[chosen]
        path_high = candidate_high[chosen]
        path_low = candidate_low[chosen]
        memoized_state_hits += transition_count - len(keys)
        states_evaluated += len(keys)
        assigned_total += component.size

    target_key = sum(np.uint64(FOLD_CAPACITIES[fold]) * state_weights[fold] for fold in range(4))
    indices = np.flatnonzero(keys == target_key)
    if len(indices) != 1 or assigned_total != sum(FOLD_CAPACITIES):
        raise DataIntegrityError("Solver did not produce one exact-capacity optimum")
    index = int(indices[0])
    packed_path = (int(path_high[index]) << 64) | int(path_low[index])
    reverse_folds: list[int] = []
    for _component in components:
        reverse_folds.append(packed_path & 0b111)
        packed_path >>= 3
    folds = tuple(reversed(reverse_folds))
    if any(fold > 4 for fold in folds) or packed_path:
        raise DataIntegrityError("Solver produced an invalid packed assignment")
    packed_cost = int(costs[index])
    return _Solution(
        folds=folds,
        states_evaluated=states_evaluated,
        memoized_state_hits=memoized_state_hits,
        moved_records=packed_cost // _COST_RADIX,
        moved_categories=packed_cost % _COST_RADIX,
    )


def build_fold_amendment_proposal(
    repo_root: str | Path,
    *,
    expected_hashes: FrozenInputHashes = PINNED_INPUT_HASHES,
) -> dict[str, Any]:
    """Reproduce the advisory fold proposal without writing or activating it."""

    root = Path(repo_root)
    if not root.is_dir() or root.is_symlink():
        raise DataIntegrityError("Repository root must be a real directory")
    relative_paths = {
        "manifest": "data/manifests/lefood_v1_manifest.csv",
        "duplicate_candidates": "data/manifests/lefood_v1_duplicate_candidates.csv",
        "audit_report": "data/manifests/lefood_v1_audit.json",
        "frozen_folds": "configs/frozen_folds.json",
    }
    paths = {name: _required_file(root, relative) for name, relative in relative_paths.items()}
    actual_hashes = {
        "manifest": _verify_hash(paths["manifest"], expected_hashes.manifest, "Manifest"),
        "duplicate_candidates": _verify_hash(
            paths["duplicate_candidates"],
            expected_hashes.duplicate_candidates,
            "Duplicate candidates",
        ),
        "audit_report": _verify_hash(
            paths["audit_report"], expected_hashes.audit_report, "Audit report"
        ),
        "frozen_folds": _verify_hash(
            paths["frozen_folds"], expected_hashes.frozen_folds, "Frozen folds"
        ),
    }
    records = _read_proposal_manifest(paths["manifest"])
    if len(records) != 524:
        raise DataIntegrityError(f"Manifest must contain 524 matched pairs, found {len(records)}")
    category_to_fold, fold_counts, category_counts = _load_frozen_assignment(
        paths["frozen_folds"], records
    )
    duplicate_rows, group_categories, crossing_groups = _load_duplicate_rows(
        paths["duplicate_candidates"], records, category_to_fold
    )
    _validate_audit(
        paths["audit_report"],
        records,
        duplicate_rows,
        group_categories,
        crossing_groups,
        fold_counts,
    )
    if len(duplicate_rows) != 10 or len(group_categories) != 9 or crossing_groups != 6:
        raise DataIntegrityError("Reviewed duplicate evidence differs from the frozen data gate")
    components, linked_components = _make_components(
        group_categories, category_to_fold, category_counts
    )
    solution = _solve(components)

    category_assignment = {
        category: fold
        for component, fold in zip(components, solution.folds, strict=True)
        for category in component.categories
    }
    candidate_folds: dict[str, dict[str, Any]] = {}
    for fold in range(5):
        categories = sorted(
            category
            for category, assigned_fold in category_assignment.items()
            if assigned_fold == fold
        )
        count = sum(category_counts[category] for category in categories)
        if count != FOLD_CAPACITIES[fold]:
            raise DataIntegrityError(f"Candidate fold {fold} does not meet its exact capacity")
        candidate_folds[str(fold)] = {"categories": categories, "n": count}
    for linked in linked_components:
        if len({category_assignment[category] for category in linked}) != 1:
            raise DataIntegrityError(
                "Candidate split separates a duplicate-linked category component"
            )

    moved_categories = [
        {
            "category": category,
            "n": category_counts[category],
            "from_fold": category_to_fold[category],
            "to_fold": category_assignment[category],
        }
        for category in sorted(category_assignment)
        if category_to_fold[category] != category_assignment[category]
    ]
    moved_record_total = sum(
        category_counts[category]
        for category in category_assignment
        if category_to_fold[category] != category_assignment[category]
    )
    if moved_record_total != solution.moved_records:
        raise DataIntegrityError("Solver record objective disagrees with the materialized proposal")
    if len(moved_categories) != solution.moved_categories:
        raise DataIntegrityError(
            "Solver category objective disagrees with the materialized proposal"
        )

    return {
        "schema_version": "1.0",
        "status": ADVISORY_STATUS,
        "binding": False,
        "created_date": "2026-09-19",
        "reason": (
            "Six confirmed near-duplicate image components cross the currently frozen "
            "category-disjoint folds."
        ),
        "warning": (
            "This advisory result does not amend configs/frozen_folds.json or "
            "src/plategauge/folds.py. No training or outer-fold evaluation may begin until "
            "an amendment is explicitly approved, recorded, and applied consistently."
        ),
        "inputs": {
            "manifest": relative_paths["manifest"],
            "manifest_sha256": actual_hashes["manifest"],
            "duplicate_candidates": relative_paths["duplicate_candidates"],
            "duplicate_candidates_sha256": actual_hashes["duplicate_candidates"],
            "audit_report": relative_paths["audit_report"],
            "audit_report_sha256": actual_hashes["audit_report"],
        },
        "constraints": {
            "retain_all_valid_records": 514,
            "keep_categories_atomic": True,
            "keep_duplicate_induced_category_components_atomic": True,
            "fold_sizes": list(FOLD_CAPACITIES),
        },
        "optimization": {
            "method": (
                "deterministic exhaustive dynamic programming over connected category "
                "components and remaining fold capacities"
            ),
            "objective_order": [
                "minimize number of records moved from the preregistered fold assignment",
                "then minimize number of categories moved",
            ],
            "states_evaluated": solution.states_evaluated,
            "memoized_state_hits": solution.memoized_state_hits,
            "optimal_moved_records": solution.moved_records,
            "optimal_moved_categories": solution.moved_categories,
        },
        "duplicate_induced_category_components": [list(item) for item in linked_components],
        "candidate_folds": candidate_folds,
        "moved_categories": moved_categories,
    }
