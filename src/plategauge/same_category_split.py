"""Freeze and validate the secondary same-category diagnostic split.

This module is deliberately isolated from the confirmatory experiment runner.
It creates a row-level diagnostic assignment without fitting a model or reading
any inner/outer prediction artifact.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

FOLD_COUNT = 5
METHOD_VERSION = "duplicate-component-balanced-greedy/v1"
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class SplitRow:
    """The manifest fields permitted to influence the diagnostic split."""

    sample_id: str
    category: str
    duplicate_group: str

    @property
    def component_id(self) -> str:
        if self.duplicate_group:
            return f"duplicate:{self.duplicate_group}"
        return f"singleton:{self.sample_id}"


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of a file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_key(seed: int, *parts: str) -> str:
    return hashlib.sha256("|".join((str(seed), *parts)).encode("utf-8")).hexdigest()


def _read_valid_rows(path: Path) -> list[SplitRow]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"sample_id", "category", "duplicate_group", "is_valid"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"Manifest is missing required columns: {sorted(required)}")
        rows = [
            SplitRow(
                sample_id=row["sample_id"],
                category=row["category"],
                duplicate_group=row["duplicate_group"],
            )
            for row in reader
            if row["is_valid"].strip().lower() == "true"
        ]
    if not rows:
        raise ValueError("Manifest contains no valid rows")
    sample_ids = [row.sample_id for row in rows]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("Valid manifest sample IDs are not unique")
    return rows


def _components(rows: list[SplitRow]) -> dict[str, list[SplitRow]]:
    components: dict[str, list[SplitRow]] = defaultdict(list)
    for row in rows:
        components[row.component_id].append(row)
    return dict(components)


def assign_same_category_folds(rows: list[SplitRow], seed: int) -> dict[str, int]:
    """Assign duplicate-atomic rows while balancing each category across folds.

    Multi-row duplicate components are placed first because they constrain one
    or more categories simultaneously. Candidate folds minimize, in order, the
    affected categories' count ranges, their squared count concentration, the
    total fold load, and a seed-derived tie key. Remaining singleton components
    are then placed category by category into that category's least-populated
    fold, with total load and a seed-derived key breaking ties.
    """

    components = _components(rows)
    category_counts: dict[str, list[int]] = defaultdict(lambda: [0] * FOLD_COUNT)
    total_counts = [0] * FOLD_COUNT
    component_fold: dict[str, int] = {}

    multi_components = [item for item in components.items() if len(item[1]) > 1]
    multi_components.sort(
        key=lambda item: (
            -len(item[1]),
            _stable_key(seed, "multi-order", item[0]),
            item[0],
        )
    )
    for component_id, component_rows in multi_components:
        contributions = Counter(row.category for row in component_rows)
        candidates: list[tuple[tuple[int, int, int, str, int], int]] = []
        for fold in range(FOLD_COUNT):
            ranges = 0
            concentration = 0
            for category, amount in contributions.items():
                proposed = list(category_counts[category])
                proposed[fold] += amount
                ranges += max(proposed) - min(proposed)
                concentration += sum(value * value for value in proposed)
            score = (
                ranges,
                concentration,
                total_counts[fold],
                _stable_key(seed, "multi-fold", component_id, str(fold)),
                fold,
            )
            candidates.append((score, fold))
        selected = min(candidates)[1]
        component_fold[component_id] = selected
        for category, amount in contributions.items():
            category_counts[category][selected] += amount
        total_counts[selected] += len(component_rows)

    singletons_by_category: dict[str, list[str]] = defaultdict(list)
    for component_id, component_rows in components.items():
        if len(component_rows) == 1:
            singletons_by_category[component_rows[0].category].append(component_id)

    for category in sorted(singletons_by_category):
        ordered = sorted(
            singletons_by_category[category],
            key=lambda value: (_stable_key(seed, "single-order", category, value), value),
        )
        for component_id in ordered:
            selected = min(
                range(FOLD_COUNT),
                key=lambda fold: (
                    category_counts[category][fold],
                    total_counts[fold],
                    _stable_key(seed, "single-fold", category, component_id, str(fold)),
                    fold,
                ),
            )
            component_fold[component_id] = selected
            category_counts[category][selected] += 1
            total_counts[selected] += 1

    return {row.sample_id: component_fold[row.component_id] for row in rows}


def validate_assignment(
    rows: list[SplitRow], assignments: dict[str, int]
) -> dict[str, Any]:
    """Validate coverage, duplicate atomicity, and category balance."""

    expected = {row.sample_id for row in rows}
    assigned = set(assignments)
    coverage_ok = assigned == expected
    fold_range_ok = all(
        isinstance(fold, int) and not isinstance(fold, bool) and 0 <= fold < FOLD_COUNT
        for fold in assignments.values()
    )

    components = _components(rows)
    atomicity_violations = sorted(
        component_id
        for component_id, component_rows in components.items()
        if len({assignments.get(row.sample_id) for row in component_rows}) != 1
    )

    rows_by_category: dict[str, list[SplitRow]] = defaultdict(list)
    for row in rows:
        rows_by_category[row.category].append(row)

    category_summary: dict[str, dict[str, Any]] = {}
    category_balance_ok = True
    category_population_ok = True
    for category in sorted(rows_by_category):
        category_rows = rows_by_category[category]
        fold_counts = [0] * FOLD_COUNT
        component_contributions: Counter[str] = Counter()
        for row in category_rows:
            component_contributions[row.component_id] += 1
            fold = assignments.get(row.sample_id)
            if isinstance(fold, int) and not isinstance(fold, bool) and 0 <= fold < FOLD_COUNT:
                fold_counts[fold] += 1
        atomic_component_count = len(component_contributions)
        maximum_populatable = min(FOLD_COUNT, atomic_component_count)
        populated = sum(value > 0 for value in fold_counts)
        largest_atomic_contribution = max(component_contributions.values())
        count_range = max(fold_counts) - min(fold_counts)
        balanced = count_range <= largest_atomic_contribution
        population_complete = populated == maximum_populatable
        category_balance_ok &= balanced
        category_population_ok &= population_complete
        category_summary[category] = {
            "n": len(category_rows),
            "atomic_component_count": atomic_component_count,
            "maximum_populatable_folds": maximum_populatable,
            "populated_folds": populated,
            "fold_counts": {str(fold): fold_counts[fold] for fold in range(FOLD_COUNT)},
            "count_range": count_range,
            "largest_atomic_contribution": largest_atomic_contribution,
            "balanced_within_atomic_constraint": balanced,
            "maximum_population_achieved": population_complete,
        }

    total_fold_counts = Counter(assignments.values())
    overall_fold_counts = {
        str(fold): total_fold_counts.get(fold, 0) for fold in range(FOLD_COUNT)
    }
    checks = {
        "complete_unique_coverage": coverage_ok,
        "fold_ids_in_range": fold_range_ok,
        "duplicate_components_atomic": not atomicity_violations,
        "category_balance_within_atomic_constraint": category_balance_ok,
        "maximum_category_fold_population_achieved": category_population_ok,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "valid_rows": len(rows),
        "categories": len(rows_by_category),
        "atomic_components": len(components),
        "multi_row_duplicate_components": sum(len(value) > 1 for value in components.values()),
        "atomicity_violations": atomicity_violations,
        "fold_counts": overall_fold_counts,
        "fold_count_range": max(overall_fold_counts.values())
        - min(overall_fold_counts.values()),
        "category_summary": category_summary,
    }


def _load_run_binding(path: Path) -> dict[str, Any]:
    raw_payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError("Confirmatory run binding must be a JSON object")
    payload = cast(dict[str, Any], raw_payload)
    protocol = payload.get("protocol")
    if not isinstance(protocol, dict):
        raise ValueError("Confirmatory run binding is missing its protocol")
    input_hashes = protocol.get("input_hashes")
    if not isinstance(input_hashes, dict) or not input_hashes:
        raise ValueError("Confirmatory run binding has no protocol input hashes")
    seed = protocol.get("confirmatory_seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("Confirmatory run binding has no integer seed")
    return payload


def build_split_artifact(manifest_path: Path, run_path: Path) -> dict[str, Any]:
    """Build a deterministic split bound to the frozen data/protocol, not a runner."""

    run = _load_run_binding(run_path)
    protocol = run["protocol"]
    manifest_hash = sha256_file(manifest_path)
    if protocol["input_hashes"].get("manifest") != manifest_hash:
        raise ValueError("Manifest hash does not match the active confirmatory run binding")

    rows = _read_valid_rows(manifest_path)
    seed = protocol["confirmatory_seed"]
    assignments = assign_same_category_folds(rows, seed)
    validation = validate_assignment(rows, assignments)
    if not validation["passed"]:
        raise ValueError("Generated same-category assignment failed validation")

    components = _components(rows)
    binding = {
        "confirmatory_seed": seed,
        "confirmatory_protocol_id": protocol.get("protocol_id"),
        "protocol_input_hashes": dict(sorted(protocol["input_hashes"].items())),
        "manifest_sha256": manifest_hash,
    }
    assignment_rows = [
        {
            "sample_id": row.sample_id,
            "category": row.category,
            "component_id": row.component_id,
            "diagnostic_fold": assignments[row.sample_id],
        }
        for row in sorted(rows, key=lambda value: value.sample_id)
    ]
    core: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "frozen_pre_outcome_secondary_diagnostic",
        "purpose": "same-category diagnostic only; never replaces category-disjoint primary result",
        "method": {
            "version": METHOD_VERSION,
            "fold_count": FOLD_COUNT,
            "outcomes_used": False,
            "duplicate_policy": "all rows in a duplicate component share one fold",
            "small_category_policy": (
                "populate min(5, atomic_component_count) distinct folds; folds that cannot be "
                "populated remain empty"
            ),
            "balance_policy": (
                "multi-row components first by affected-category balance; remaining singletons "
                "go to the category's least-populated fold; seeded hashes break exact ties"
            ),
        },
        "bindings": binding,
        "counts": {
            "valid_rows": len(rows),
            "categories": len({row.category for row in rows}),
            "atomic_components": len(components),
            "multi_row_duplicate_components": sum(len(value) > 1 for value in components.values()),
            "fold_counts": validation["fold_counts"],
        },
        "category_summary": validation["category_summary"],
        "assignments": assignment_rows,
    }
    core["split_id"] = _canonical_sha256(core)
    return core


def validate_split_artifact(
    artifact: dict[str, Any], manifest_path: Path, run_path: Path
) -> dict[str, Any]:
    """Rebuild and compare the artifact without reading experiment outcomes."""

    expected = build_split_artifact(manifest_path, run_path)
    rows = _read_valid_rows(manifest_path)
    raw_assignments = artifact.get("assignments")
    assignments: dict[str, int] = {}
    if isinstance(raw_assignments, list):
        for value in raw_assignments:
            if isinstance(value, dict):
                sample_id = value.get("sample_id")
                fold = value.get("diagnostic_fold")
                if isinstance(sample_id, str) and isinstance(fold, int) and not isinstance(fold, bool):
                    assignments[sample_id] = fold
    assignment_validation = validate_assignment(rows, assignments)
    checks = {
        "exact_deterministic_reproduction": artifact == expected,
        "split_id_matches_reproduction": artifact.get("split_id") == expected["split_id"],
        **assignment_validation["checks"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": all(checks.values()),
        "checks": checks,
        "split_id": artifact.get("split_id"),
        "expected_split_id": expected["split_id"],
        "assignment_validation": assignment_validation,
    }


def write_immutable_json(path: Path, payload: dict[str, Any]) -> None:
    """Write canonical pretty JSON, refusing to replace different content."""

    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError(f"Refusing to overwrite different frozen artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")
