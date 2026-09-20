"""Build and verify the browser benchmark explorer's frozen evidence payload."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .data import sha256_file
from .errors import DataIntegrityError

SCHEMA_VERSION = 1
DEFAULT_OUTPUT = Path("web/src/generated/benchmarkEvidence.json")
PUBLIC_OUTPUT = Path("web/public/evidence/benchmark-evidence.json")
RESULTS_PATH = Path("reports/results.json")
ERROR_ANALYSIS_PATH = Path("reports/error_analysis.json")
ERROR_ANNOTATIONS_PATH = Path("reports/error_review_annotations.csv")
MANIFEST_PATH = Path("data/manifests/lefood_v1_manifest.csv")
BROWSER_BENCHMARK_PATH = Path("reports/browser_benchmark.json")
EXPORT_EVIDENCE_PATH = Path("artifacts/plategauge.onnx.evidence.json")
SELECTION_PATH = Path("configs/web_benchmark_selection.json")
ROBUSTNESS_PATH = Path("reports/robustness.json")
TARGET_SLICES = (
    ("zero", "Exact zero"),
    ("(0,.25]", "(0, 0.25]"),
    ("(.25,.50]", "(0.25, 0.50]"),
    ("(.50,.75]", "(0.50, 0.75]"),
    ("(.75,1)", "(0.75, 1)"),
    ("one", "Exact one"),
)

# These are the seven model/control workloads plus the observer-score contextual
# reference in reports/results.json.  Keeping public labels and roles here makes
# the intended interpretation independently testable rather than UI copy only.
WORKLOAD_SPECS = {
    "observer_score_context_only": {
        "label": "Observer score",
        "role": "contextual_reference",
        "caveat": (
            "Contextual observer-score reference only; it is not a deployable model "
            "and is not available from the image pair alone."
        ),
    },
    "after_only_mobilenet": {
        "label": "After-only MobileNet",
        "role": "required_ablation",
        "caveat": "Uses only the after image and is the required paired-value comparator.",
    },
    "frozen_paired_dinov2": {
        "label": "Frozen paired DINOv2",
        "role": "heavy_representation_reference",
        "caveat": "Accuracy reference only; it is not the browser deployment model.",
    },
    "paired_mobilenet": {
        "label": "Paired MobileNet",
        "role": "primary_confirmatory_model",
        "caveat": (
            "Primary confirmatory paired model; it did not outperform the after-only "
            "ablation under the frozen category-shift protocol."
        ),
    },
    "paired_resnet50": {
        "label": "Paired ResNet-50",
        "role": "architecture_family_control",
        "caveat": "Single-task paired reproduction used as an architecture-family control.",
    },
    "handcrafted_ridge": {
        "label": "Handcrafted paired Ridge",
        "role": "non_neural_baseline",
        "caveat": "Best specified non-neural baseline on the same frozen outer folds.",
    },
    "training_median": {
        "label": "Training-fold median",
        "role": "constant_baseline",
        "caveat": "Constant prediction fitted only from each outer training partition.",
    },
    "fixed_within_category_wrong_pair": {
        "label": "Wrong-pair control",
        "role": "destructive_mismatch_control",
        "caveat": (
            "Destructive input/target mismatch in both training and evaluation; its poor "
            "result is not evidence that the before image adds predictive value."
        ),
    },
}

ROBUSTNESS_CONDITIONS = {
    "clean": {
        "label": "Clean all-data model evaluation",
        "role": "clean_reference",
    },
    "after_gaussian_blur_sigma_1": {
        "label": "After-image Gaussian blur (sigma=1)",
        "role": "routine_perturbation",
    },
    "misuse_same_before_image": {
        "label": "Same image supplied twice",
        "role": "misuse_test",
    },
    "misuse_swapped_order": {
        "label": "Before/after order swapped",
        "role": "misuse_test",
    },
    "misuse_unrelated_after": {
        "label": "Unrelated after image",
        "role": "misuse_test",
    },
}


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataIntegrityError(f"Cannot read JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataIntegrityError(f"JSON root must be an object: {path}")
    return payload


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DataIntegrityError(f"Expected an object at {label}")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise DataIntegrityError(f"Expected a list at {label}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise DataIntegrityError(f"Expected a non-empty string at {label}")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataIntegrityError(f"Expected an integer at {label}")
    return int(value)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise DataIntegrityError(f"Expected a boolean at {label}")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataIntegrityError(f"Expected a number at {label}")
    result = float(value)
    if not math.isfinite(result):
        raise DataIntegrityError(f"Expected a finite number at {label}")
    return result


def _path_value(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            raise DataIntegrityError(f"Missing canonical evidence field: {path}")
        value = value[component]
    return value


def _path_number(payload: dict[str, Any], path: str) -> float:
    return _number(_path_value(payload, path), path)


def _path_integer(payload: dict[str, Any], path: str) -> int:
    return _integer(_path_value(payload, path), path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise DataIntegrityError(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise DataIntegrityError(f"Cannot read CSV {path}: {exc}") from exc


def _csv_float(row: dict[str, str], field: str, path: Path) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise DataIntegrityError(f"Invalid {field} in {path}: {row.get(field)!r}") from exc
    if not math.isfinite(value):
        raise DataIntegrityError(f"Non-finite {field} in {path}")
    return value


def _csv_int(row: dict[str, str], field: str, path: Path) -> int:
    try:
        return int(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise DataIntegrityError(f"Invalid {field} in {path}: {row.get(field)!r}") from exc


def _compact_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _prediction_path(fold: int, workload: str) -> Path:
    task = f"outer.fold-{fold}.{workload}"
    return Path("reports/experiments/confirmatory/tasks") / task / "workload/predictions.csv"


def _prediction_hashes(results: dict[str, Any]) -> dict[str, str]:
    artifacts = _list(_path_value(results, "provenance.outer_artifacts"), "provenance.outer_artifacts")
    hashes: dict[str, str] = {}
    for index, raw_record in enumerate(artifacts):
        record = _object(raw_record, f"provenance.outer_artifacts[{index}]")
        task_id = _string(record.get("task_id"), f"outer_artifacts[{index}].task_id")
        digest = _string(
            record.get("predictions_sha256"),
            f"outer_artifacts[{index}].predictions_sha256",
        )
        if task_id in hashes:
            raise DataIntegrityError(f"Duplicate outer-artifact task ID: {task_id}")
        hashes[task_id] = digest
    return hashes


def _load_predictions(
    root: Path,
    workload: str,
    expected_hashes: dict[str, str],
    source_hashes: dict[str, str],
) -> dict[str, dict[str, str]]:
    predictions: dict[str, dict[str, str]] = {}
    for fold in range(5):
        relative = _prediction_path(fold, workload)
        path = root / relative
        task_id = f"outer.fold-{fold}.{workload}"
        expected_hash = expected_hashes.get(task_id)
        if expected_hash is None:
            raise DataIntegrityError(f"Results provenance omits {task_id}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise DataIntegrityError(
                f"Prediction hash differs from frozen results provenance: {relative}"
            )
        source_hashes[relative.as_posix()] = actual_hash
        for row in _read_csv(path):
            sample_id = _string(row.get("sample_id"), f"{relative}:sample_id")
            if sample_id in predictions:
                raise DataIntegrityError(f"Duplicate {workload} prediction: {sample_id}")
            if row.get("workload") != workload:
                raise DataIntegrityError(f"Workload mismatch in {relative}: {sample_id}")
            if _csv_int(row, "outer_fold", path) != fold:
                raise DataIntegrityError(f"Fold mismatch in {relative}: {sample_id}")
            for field in ("target", "q05", "q50", "q95"):
                _csv_float(row, field, path)
            predictions[sample_id] = row
    return predictions


def _load_manifest(root: Path, source_hashes: dict[str, str]) -> dict[str, dict[str, str]]:
    path = root / MANIFEST_PATH
    source_hashes[MANIFEST_PATH.as_posix()] = sha256_file(path)
    rows: dict[str, dict[str, str]] = {}
    for row in _read_csv(path):
        sample_id = _string(row.get("sample_id"), f"{MANIFEST_PATH}:sample_id")
        if sample_id in rows:
            raise DataIntegrityError(f"Duplicate manifest sample ID: {sample_id}")
        if row.get("is_valid", "").lower() == "true":
            rows[sample_id] = row
    return rows


def _load_annotations(root: Path, source_hashes: dict[str, str]) -> dict[str, dict[str, str]]:
    path = root / ERROR_ANNOTATIONS_PATH
    source_hashes[ERROR_ANNOTATIONS_PATH.as_posix()] = sha256_file(path)
    rows: dict[str, dict[str, str]] = {}
    for row in _read_csv(path):
        sample_id = _string(row.get("sample_id"), f"{ERROR_ANNOTATIONS_PATH}:sample_id")
        if sample_id in rows:
            raise DataIntegrityError(f"Duplicate error-review annotation: {sample_id}")
        rows[sample_id] = row
    return rows


def _assert_prediction_alignment(
    manifest: dict[str, dict[str, str]],
    paired: dict[str, dict[str, str]],
    after_only: dict[str, dict[str, str]],
    expected_count: int,
) -> None:
    populations = {
        "manifest": set(manifest),
        "paired": set(paired),
        "after_only": set(after_only),
    }
    if any(len(values) != expected_count for values in populations.values()):
        raise DataIntegrityError(
            "Canonical populations do not have the frozen valid-pair count: "
            + repr({name: len(values) for name, values in populations.items()})
        )
    if len({frozenset(values) for values in populations.values()}) != 1:
        raise DataIntegrityError("Manifest and paired/after-only prediction populations differ")
    for sample_id, paired_row in paired.items():
        after_row = after_only[sample_id]
        manifest_row = manifest[sample_id]
        canonical_category = manifest_row.get("category")
        canonical_fold = _csv_int(manifest_row, "outer_fold", MANIFEST_PATH)
        canonical_target = _csv_float(manifest_row, "leftover_fraction", MANIFEST_PATH)
        for label, row in (("paired", paired_row), ("after-only", after_row)):
            if row.get("category") != canonical_category:
                raise DataIntegrityError(f"Category mismatch for {sample_id} in {label}")
            if _csv_int(row, "outer_fold", Path(label)) != canonical_fold:
                raise DataIntegrityError(f"Fold mismatch for {sample_id} in {label}")
            if not math.isclose(
                _csv_float(row, "target", Path(label)),
                canonical_target,
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise DataIntegrityError(f"Target mismatch for {sample_id} in {label}")


def _workload_evidence(
    results: dict[str, Any],
    *,
    valid_pairs: int,
    category_count: int,
) -> list[dict[str, Any]]:
    workloads = _object(results.get("workloads"), "results.workloads")
    if set(workloads) != set(WORKLOAD_SPECS):
        raise DataIntegrityError(
            "Frozen result workloads differ from the explicit public evidence contract: "
            f"expected={sorted(WORKLOAD_SPECS)}, observed={sorted(workloads)}"
        )
    records: list[dict[str, Any]] = []
    for workload_id, spec in WORKLOAD_SPECS.items():
        workload = _object(workloads.get(workload_id), f"workloads.{workload_id}")
        overall = _object(workload.get("overall"), f"workloads.{workload_id}.overall")
        observed_n = _integer(overall.get("n"), f"workloads.{workload_id}.overall.n")
        observed_categories = _integer(
            overall.get("category_count"),
            f"workloads.{workload_id}.overall.category_count",
        )
        if observed_n != valid_pairs or observed_categories != category_count:
            raise DataIntegrityError(
                f"Workload {workload_id} differs from the frozen evaluation population"
            )
        records.append(
            {
                "id": workload_id,
                "label": spec["label"],
                "role": spec["role"],
                "count": observed_n,
                "categoryCount": observed_categories,
                "macroCategoryMae": _number(
                    overall.get("macro_category_mae"),
                    f"workloads.{workload_id}.overall.macro_category_mae",
                ),
                "caveat": spec["caveat"],
            }
        )
    return sorted(records, key=lambda record: (float(record["macroCategoryMae"]), str(record["id"])))


def _category_evidence(
    results: dict[str, Any],
    paired: dict[str, dict[str, str]],
    after_only: dict[str, dict[str, str]],
    *,
    expected_categories: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for sample_id, row in paired.items():
        category = _string(row.get("category"), f"paired.{sample_id}.category")
        grouped.setdefault(category, []).append(sample_id)
    if len(grouped) != expected_categories:
        raise DataIntegrityError(
            f"Prediction-derived category count differs from frozen results: {len(grouped)}"
        )

    workloads = _object(results.get("workloads"), "results.workloads")
    paired_categories = _object(
        _object(workloads.get("paired_mobilenet"), "workloads.paired_mobilenet").get(
            "per_category"
        ),
        "workloads.paired_mobilenet.per_category",
    )
    after_categories = _object(
        _object(workloads.get("after_only_mobilenet"), "workloads.after_only_mobilenet").get(
            "per_category"
        ),
        "workloads.after_only_mobilenet.per_category",
    )
    if set(grouped) != set(paired_categories) or set(grouped) != set(after_categories):
        raise DataIntegrityError("Prediction-derived and frozen result category sets differ")

    records: list[dict[str, Any]] = []
    for category in sorted(grouped):
        sample_ids = grouped[category]
        paired_mae = sum(
            abs(
                _csv_float(paired[sample_id], "q50", Path("paired"))
                - _csv_float(paired[sample_id], "target", Path("paired"))
            )
            for sample_id in sample_ids
        ) / len(sample_ids)
        after_mae = sum(
            abs(
                _csv_float(after_only[sample_id], "q50", Path("after-only"))
                - _csv_float(after_only[sample_id], "target", Path("after-only"))
            )
            for sample_id in sample_ids
        ) / len(sample_ids)
        frozen_paired = _object(paired_categories[category], f"paired.per_category.{category}")
        frozen_after = _object(after_categories[category], f"after.per_category.{category}")
        expected_paired = _number(
            frozen_paired.get("micro_mae"), f"paired.per_category.{category}.micro_mae"
        )
        expected_after = _number(
            frozen_after.get("micro_mae"), f"after.per_category.{category}.micro_mae"
        )
        expected_support = _integer(
            frozen_paired.get("n"), f"paired.per_category.{category}.n"
        )
        if (
            expected_support != len(sample_ids)
            or _integer(frozen_after.get("n"), f"after.per_category.{category}.n")
            != len(sample_ids)
            or not math.isclose(paired_mae, expected_paired, rel_tol=0.0, abs_tol=1e-15)
            or not math.isclose(after_mae, expected_after, rel_tol=0.0, abs_tol=1e-15)
        ):
            raise DataIntegrityError(
                f"Prediction-derived category metrics differ from frozen results: {category}"
            )
        records.append(
            {
                "category": category,
                "support": len(sample_ids),
                "pairedMae": paired_mae,
                "afterOnlyMae": after_mae,
                "pairedMinusAfterOnly": paired_mae - after_mae,
            }
        )
    return records


def _endpoint_prevalence(
    paired: dict[str, dict[str, str]],
    *,
    valid_pairs: int,
) -> dict[str, Any]:
    targets = [_csv_float(row, "target", Path("paired")) for row in paired.values()]
    exact_zero = sum(target == 0.0 for target in targets)
    exact_one = sum(target == 1.0 for target in targets)
    endpoint_total = exact_zero + exact_one
    interior = len(targets) - endpoint_total
    if len(targets) != valid_pairs:
        raise DataIntegrityError("Endpoint prevalence population differs from frozen results")
    return {
        "exactZero": exact_zero,
        "exactOne": exact_one,
        "interior": interior,
        "endpointTotal": endpoint_total,
        "total": valid_pairs,
        "endpointFraction": endpoint_total / valid_pairs,
        "caveat": (
            "Exact zero and exact one are endpoint targets; their prevalence can make aggregate "
            "error look better than performance on interior leftover fractions."
        ),
    }


def _robustness_evidence(robustness: dict[str, Any]) -> dict[str, Any]:
    if (
        robustness.get("kind") != "frozen_final_model_robustness"
        or robustness.get("status") != "complete"
    ):
        raise DataIntegrityError("Robustness evidence is not the completed frozen report")
    raw_conditions = _list(robustness.get("conditions"), "robustness.conditions")
    by_name: dict[str, dict[str, Any]] = {}
    for index, raw_condition in enumerate(raw_conditions):
        condition = _object(raw_condition, f"robustness.conditions[{index}]")
        name = _string(condition.get("name"), f"robustness.conditions[{index}].name")
        if name in by_name:
            raise DataIntegrityError(f"Duplicate robustness condition: {name}")
        by_name[name] = condition
    missing = sorted(set(ROBUSTNESS_CONDITIONS).difference(by_name))
    if missing:
        raise DataIntegrityError(f"Frozen robustness report lacks public conditions: {missing}")

    records: list[dict[str, Any]] = []
    for name, spec in ROBUSTNESS_CONDITIONS.items():
        condition = by_name[name]
        record: dict[str, Any] = {
            "id": name,
            "label": spec["label"],
            "role": spec["role"],
            "count": _integer(condition.get("n"), f"robustness.{name}.n"),
            "categoryCount": _integer(
                condition.get("category_count"), f"robustness.{name}.category_count"
            ),
            "macroCategoryMae": _number(
                condition.get("macro_category_mae"),
                f"robustness.{name}.macro_category_mae",
            ),
            "deltaFromClean": _number(
                condition.get("delta_macro_category_mae_from_clean"),
                f"robustness.{name}.delta_macro_category_mae_from_clean",
            ),
            "thresholdBreached": _boolean(
                condition.get("exceeds_routine_downgrade_threshold"),
                f"robustness.{name}.exceeds_routine_downgrade_threshold",
            ),
        }
        threshold = condition.get("routine_downgrade_threshold")
        if threshold is not None:
            record["downgradeThreshold"] = _number(
                threshold, f"robustness.{name}.routine_downgrade_threshold"
            )
        misuse_rule = condition.get("misuse_rule")
        if misuse_rule is not None:
            record["misuseRule"] = _string(misuse_rule, f"robustness.{name}.misuse_rule")
        records.append(record)

    after_blur = by_name["after_gaussian_blur_sigma_1"]
    if (
        after_blur.get("group") != "routine_perturbation"
        or after_blur.get("mode") != "after_only"
        or _number(after_blur.get("parameter"), "robustness.after_blur.parameter") != 1.0
        or after_blur.get("routine_downgrade_threshold") != 0.03
        or after_blur.get("exceeds_routine_downgrade_threshold") is not True
    ):
        raise DataIntegrityError("After-image blur robustness condition violates the frozen contract")
    for name in (
        "misuse_same_before_image",
        "misuse_swapped_order",
        "misuse_unrelated_after",
    ):
        if by_name[name].get("group") != "misuse":
            raise DataIntegrityError(f"Robustness condition is not labeled misuse: {name}")

    return {
        "downgradeRequired": _boolean(
            robustness.get("robustness_downgrade_required"),
            "robustness.robustness_downgrade_required",
        ),
        "records": records,
        "caveat": (
            "These measurements use the final model trained on all 514 pairs and are not a "
            "held-out generalization estimate. Misuse conditions are diagnostics, not routine "
            "robustness-gate inputs."
        ),
    }


def _example(
    *,
    sample_id: str,
    kind: str,
    rank: int,
    note: str,
    manifest: dict[str, dict[str, str]],
    paired: dict[str, dict[str, str]],
    after_only: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if sample_id not in manifest or sample_id not in paired or sample_id not in after_only:
        raise DataIntegrityError(f"Selected web example is absent from canonical evidence: {sample_id}")
    manifest_row = manifest[sample_id]
    paired_row = paired[sample_id]
    after_row = after_only[sample_id]
    before_mass = _csv_float(manifest_row, "before_mass_g", MANIFEST_PATH)
    after_mass = _csv_float(manifest_row, "after_mass_g", MANIFEST_PATH)
    target = _csv_float(manifest_row, "leftover_fraction", MANIFEST_PATH)
    if before_mass <= 0 or not math.isclose(
        after_mass / before_mass,
        target,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise DataIntegrityError(f"Manifest target formula fails for selected example: {sample_id}")
    return {
        "id": sample_id,
        "kind": kind,
        "rank": rank,
        "foodName": _string(manifest_row.get("food_name"), f"{sample_id}.food_name"),
        "category": _string(manifest_row.get("category"), f"{sample_id}.category"),
        "fold": _csv_int(manifest_row, "outer_fold", MANIFEST_PATH),
        "beforeMassG": _compact_number(before_mass),
        "afterMassG": _compact_number(after_mass),
        "target": target,
        "pairedPrediction": _csv_float(paired_row, "q50", Path("paired")),
        "afterOnlyPrediction": _csv_float(after_row, "q50", Path("after-only")),
        "note": note,
    }


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _artifact_targets(root: Path, requested: str | Path) -> list[Path]:
    target = Path(requested)
    if not target.is_absolute():
        target = root / target
    default_target = root / DEFAULT_OUTPUT
    if target.resolve() == default_target.resolve():
        return [default_target, root / PUBLIC_OUTPUT]
    return [target]


def build_web_benchmark_evidence(repo_root: str | Path) -> dict[str, Any]:
    """Derive every browser-visible benchmark value from frozen source evidence."""

    root = Path(repo_root).resolve()
    source_hashes: dict[str, str] = {}
    canonical_json: dict[Path, dict[str, Any]] = {}
    for relative in (
        RESULTS_PATH,
        ERROR_ANALYSIS_PATH,
        BROWSER_BENCHMARK_PATH,
        EXPORT_EVIDENCE_PATH,
        SELECTION_PATH,
        ROBUSTNESS_PATH,
    ):
        path = root / relative
        canonical_json[relative] = _json_object(path)
        source_hashes[relative.as_posix()] = sha256_file(path)

    results = canonical_json[RESULTS_PATH]
    error_analysis = canonical_json[ERROR_ANALYSIS_PATH]
    browser = canonical_json[BROWSER_BENCHMARK_PATH]
    export = canonical_json[EXPORT_EVIDENCE_PATH]
    selection = canonical_json[SELECTION_PATH]
    robustness = canonical_json[ROBUSTNESS_PATH]
    if results.get("frozen") is not True or error_analysis.get("frozen") is not True:
        raise DataIntegrityError("Browser evidence requires frozen results and error analysis")
    if results.get("protocol_id") != error_analysis.get("protocol_id"):
        raise DataIntegrityError("Results and error analysis protocol IDs differ")
    if selection.get("schemaVersion") != SCHEMA_VERSION:
        raise DataIntegrityError("Unsupported web benchmark selection schema")

    expected_hashes = _prediction_hashes(results)
    paired = _load_predictions(root, "paired_mobilenet", expected_hashes, source_hashes)
    after_only = _load_predictions(root, "after_only_mobilenet", expected_hashes, source_hashes)
    manifest = _load_manifest(root, source_hashes)
    annotations = _load_annotations(root, source_hashes)
    valid_pairs = _path_integer(results, "dataset.valid_pairs")
    category_count = _path_integer(results, "dataset.categories")
    _assert_prediction_alignment(manifest, paired, after_only, valid_pairs)
    workload_evidence = _workload_evidence(
        results,
        valid_pairs=valid_pairs,
        category_count=category_count,
    )
    category_evidence = _category_evidence(
        results,
        paired,
        after_only,
        expected_categories=category_count,
    )

    successes: list[dict[str, Any]] = []
    selected_success_ids: set[str] = set()
    raw_successes = _list(selection.get("successExamples"), "successExamples")
    if len(raw_successes) != 5:
        raise DataIntegrityError("Exactly five reviewed success examples are required")
    for rank, raw_success in enumerate(raw_successes, start=1):
        success = _object(raw_success, f"successExamples[{rank - 1}]")
        sample_id = _string(success.get("sampleId"), f"successExamples[{rank - 1}].sampleId")
        if sample_id in selected_success_ids:
            raise DataIntegrityError(f"Duplicate selected success example: {sample_id}")
        selected_success_ids.add(sample_id)
        successes.append(
            _example(
                sample_id=sample_id,
                kind="representative_success",
                rank=rank,
                note=_string(success.get("note"), f"successExamples[{rank - 1}].note"),
                manifest=manifest,
                paired=paired,
                after_only=after_only,
            )
        )

    failure_records = _list(
        _path_value(error_analysis, "largest_absolute_errors.records"),
        "largest_absolute_errors.records",
    )
    if len(failure_records) < 5:
        raise DataIntegrityError("Frozen error analysis has fewer than five largest errors")
    failures: list[dict[str, Any]] = []
    selected_failure_ids: set[str] = set()
    for rank, raw_failure in enumerate(failure_records[:5], start=1):
        failure = _object(raw_failure, f"largest_absolute_errors.records[{rank - 1}]")
        sample_id = _string(failure.get("sample_id"), f"largest error rank {rank}.sample_id")
        if sample_id in selected_failure_ids or sample_id in selected_success_ids:
            raise DataIntegrityError(f"Duplicate selected web example: {sample_id}")
        selected_failure_ids.add(sample_id)
        if _integer(failure.get("rank"), f"{sample_id}.rank") != rank:
            raise DataIntegrityError(f"Frozen error rank mismatch for {sample_id}")
        prediction = _csv_float(paired[sample_id], "q50", Path("paired"))
        if not math.isclose(
            _number(failure.get("q50"), f"{sample_id}.q50"),
            prediction,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise DataIntegrityError(f"Error analysis prediction differs for {sample_id}")
        annotation = annotations.get(sample_id)
        if annotation is None:
            raise DataIntegrityError(f"Largest error lacks reviewed annotation: {sample_id}")
        if _csv_int(annotation, "rank", ERROR_ANNOTATIONS_PATH) != rank:
            raise DataIntegrityError(f"Error-review rank mismatch for {sample_id}")
        if annotation.get("review_status") != "ai_visual_review_complete_applicant_pending":
            raise DataIntegrityError(f"Error review has an unexpected status for {sample_id}")
        _string(annotation.get("tags"), f"{sample_id}.tags")
        failures.append(
            _example(
                sample_id=sample_id,
                kind="largest_error",
                rank=rank,
                note=_string(annotation.get("review_note"), f"{sample_id}.review_note"),
                manifest=manifest,
                paired=paired,
                after_only=after_only,
            )
        )

    paired_overall = _object(
        _path_value(results, "workloads.paired_mobilenet.overall"),
        "workloads.paired_mobilenet.overall",
    )
    target_slices = _object(
        _path_value(results, "workloads.paired_mobilenet.slices.target_range"),
        "workloads.paired_mobilenet.slices.target_range",
    )
    slice_metrics: list[dict[str, Any]] = []
    for source_label, public_label in TARGET_SLICES:
        record = _object(target_slices.get(source_label), f"target_range.{source_label}")
        slice_metrics.append(
            {
                "label": public_label,
                "count": _integer(record.get("n"), f"target_range.{source_label}.n"),
                "microMae": _number(
                    record.get("micro_mae"), f"target_range.{source_label}.micro_mae"
                ),
            }
        )
    if sum(int(record["count"]) for record in slice_metrics) != valid_pairs:
        raise DataIntegrityError("Target-slice counts do not sum to the frozen population")

    payload: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "provenance": {
            "kind": "derived_frozen_web_benchmark_evidence",
            "protocolId": _string(results.get("protocol_id"), "results.protocol_id"),
            "runId": _string(results.get("run_id"), "results.run_id"),
            "successSelectionPolicy": _string(
                selection.get("successSelectionPolicy"), "successSelectionPolicy"
            ),
            "sourceFiles": dict(sorted(source_hashes.items())),
        },
        "frozenMetrics": {
            "validPairs": valid_pairs,
            "categories": category_count,
            "pairedMacroMae": _number(
                paired_overall.get("macro_category_mae"), "paired.overall.macro_category_mae"
            ),
            "pairedMicroMae": _number(
                paired_overall.get("micro_mae"), "paired.overall.micro_mae"
            ),
            "pairedP90AbsoluteError": _number(
                paired_overall.get("p90_absolute_error"), "paired.overall.p90_absolute_error"
            ),
            "pairedWithinTenPoints": _number(
                paired_overall.get("within_0_10"), "paired.overall.within_0_10"
            ),
            "afterOnlyMacroMae": _path_number(
                results, "comparisons.after_only.comparator_macro_category_mae"
            ),
            "bestNonNeuralMacroMae": _path_number(
                results, "comparisons.best_non_neural.comparator_macro_category_mae"
            ),
            "pairedMinusAfterOnly": _path_number(
                results, "comparisons.after_only.bootstrap.estimate_a_minus_b"
            ),
            "pairedMinusAfterOnlyCi95": [
                _path_number(results, "comparisons.after_only.bootstrap.lower_95"),
                _path_number(results, "comparisons.after_only.bootstrap.upper_95"),
            ],
            "worstBroadTargetSliceMicroMae": _path_number(
                results, "decisions.numeric_demo.worst_broad_target_slice_micro_mae"
            ),
            "evaluationSeed": _path_integer(results, "analysis.confirmatory_seed"),
        },
        "workloadEvidence": {
            "modelAndControlWorkloadCount": len(WORKLOAD_SPECS) - 1,
            "contextualReferenceCount": 1,
            "records": workload_evidence,
        },
        "categoryComparisons": category_evidence,
        "targetSliceMetrics": slice_metrics,
        "endpointPrevalence": _endpoint_prevalence(paired, valid_pairs=valid_pairs),
        "robustnessSummary": _robustness_evidence(robustness),
        "engineeringEvidence": {
            "modelBytes": _path_integer(export, "onnx.model_bytes"),
            "maximumPytorchOnnxDrift": _path_number(export, "parity.maximum_absolute_drift"),
            "paritySampleCount": _path_integer(export, "parity.sample_count"),
            "warmP95Ms": _path_number(browser, "derived.warm_p95_ms"),
            "warmMeasurementCount": _path_integer(browser, "reported.warm_measurement_count"),
            "warmupRuns": _path_integer(browser, "reported.warmup_runs"),
            "peakMemoryMiB": _path_number(browser, "reported.peak_application_memory_mb"),
            "referenceBrowser": (
                _string(_path_value(browser, "runtime.browser_name"), "runtime.browser_name")
                + " "
                + _string(
                    _path_value(browser, "runtime.browser_version"), "runtime.browser_version"
                )
            ),
        },
        "semantics": {
            "target": (
                "leftover fraction = recorded after mass divided by recorded before mass; "
                "0 means none left and 1 means all left"
            ),
            "macroCategoryMae": (
                "Mean of the 34 per-category mean absolute errors; lower is better. A value "
                "of 0.10 is ten percentage points of absolute leftover-fraction error."
            ),
            "pairedMinusAfterOnly": (
                "Paired-model category MAE minus after-only category MAE; positive values mean "
                "the paired model was worse."
            ),
            "evaluationBoundary": (
                "All confirmatory workload and category comparisons are frozen category-disjoint "
                "outer-fold results on 514 valid LeFood pairs across categories 000-033."
            ),
            "publicClaimBoundary": (
                "Benchmark and failure-analysis evidence only; no estimator, interval, robustness, "
                "operational, impact, smartphone, UAE, clinical, or production-validity claim."
            ),
        },
        "benchmarkExamples": successes + failures,
    }
    return payload


def write_web_benchmark_evidence(
    repo_root: str | Path,
    output: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    """Write the canonical generated payload and return its evidence summary."""

    root = Path(repo_root).resolve()
    payload = build_web_benchmark_evidence(root)
    payload_bytes = _canonical_bytes(payload)
    targets = _artifact_targets(root, output)
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload_bytes)
    return {
        "status": "written",
        "path": targets[0].relative_to(root).as_posix(),
        "paths": [target.relative_to(root).as_posix() for target in targets],
        "sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "exampleCount": len(_list(payload["benchmarkExamples"], "benchmarkExamples")),
        "sourceFileCount": len(
            _object(_path_value(payload, "provenance.sourceFiles"), "provenance.sourceFiles")
        ),
    }


def verify_web_benchmark_evidence(
    repo_root: str | Path,
    artifact: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    """Fail if the checked-in browser payload differs from canonical evidence."""

    root = Path(repo_root).resolve()
    expected = build_web_benchmark_evidence(root)
    expected_bytes = _canonical_bytes(expected)
    targets = _artifact_targets(root, artifact)
    expected_hash = hashlib.sha256(expected_bytes).hexdigest()
    for target in targets:
        try:
            actual_bytes = target.read_bytes()
        except OSError as exc:
            raise DataIntegrityError(f"Cannot read generated web evidence {target}: {exc}") from exc
        if actual_bytes != expected_bytes:
            actual_hash = hashlib.sha256(actual_bytes).hexdigest()
            raise DataIntegrityError(
                "Generated web benchmark evidence is stale or edited; regenerate it from frozen "
                f"sources ({target}: expected {expected_hash}, observed {actual_hash})"
            )
    return {
        "status": "passed",
        "path": targets[0].relative_to(root).as_posix(),
        "paths": [target.relative_to(root).as_posix() for target in targets],
        "sha256": expected_hash,
        "exampleCount": len(_list(expected["benchmarkExamples"], "benchmarkExamples")),
        "sourceFileCount": len(
            _object(_path_value(expected, "provenance.sourceFiles"), "provenance.sourceFiles")
        ),
    }
