"""Frozen clean, perturbation, and misuse evaluation for the final model."""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .errors import DataIntegrityError, missing_extra
from .metrics import regression_metrics
from .release_artifacts import (
    EXPECTED_VALID_PAIRS,
    FrozenFinalArtifact,
    canonical_json_sha256,
    write_immutable_json,
)
from .robustness import (
    FROZEN_PERTURBATIONS,
    Perturbation,
    perturb_pair,
    same_image_pair,
    swapped_pair,
)
from .schema import ManifestRecord, read_manifest
from .transforms import deterministic_preprocess

ROBUSTNESS_SCHEMA_VERSION = "1.0"
ROBUSTNESS_DOWNGRADE_THRESHOLD = 0.03

BatchPredictor = Callable[[np.ndarray, np.ndarray], np.ndarray]


@dataclass(frozen=True, slots=True)
class RobustnessCondition:
    name: str
    group: Literal["clean", "routine_perturbation", "misuse"]
    perturbation: Perturbation | None = None
    misuse: Literal["same_before_image", "swapped_order", "unrelated_after"] | None = None


FROZEN_CONDITIONS: tuple[RobustnessCondition, ...] = (
    RobustnessCondition("clean", "clean"),
    *(
        RobustnessCondition(item.name, "routine_perturbation", perturbation=item)
        for item in FROZEN_PERTURBATIONS
    ),
    RobustnessCondition("misuse_same_before_image", "misuse", misuse="same_before_image"),
    RobustnessCondition("misuse_swapped_order", "misuse", misuse="swapped_order"),
    RobustnessCondition("misuse_unrelated_after", "misuse", misuse="unrelated_after"),
)


def _validated_records(manifest_path: str | Path) -> list[ManifestRecord]:
    records = sorted(
        (record for record in read_manifest(manifest_path) if record.is_valid),
        key=lambda record: record.sample_id,
    )
    if len(records) != EXPECTED_VALID_PAIRS:
        raise DataIntegrityError(
            f"Robustness evaluation requires 514 valid pairs, found {len(records)}"
        )
    if len({record.sample_id for record in records}) != EXPECTED_VALID_PAIRS:
        raise DataIntegrityError("Robustness sample identifiers are not unique")
    if len({record.category for record in records}) != 34:
        raise DataIntegrityError("Robustness evaluation requires all 34 valid categories")
    return records


def unrelated_after_mapping(records: Sequence[ManifestRecord]) -> dict[str, ManifestRecord]:
    """Return a deterministic bijection whose donor category always differs.

    Sorting by category makes each category one contiguous block. Rotating by
    the largest category support yields a cross-category derangement because no
    category occupies more than half of the 514-pair benchmark.
    """

    ordered = sorted(records, key=lambda record: (record.category, record.sample_id))
    if not ordered:
        raise DataIntegrityError("Cannot construct unrelated pairs from an empty benchmark")
    supports: dict[str, int] = {}
    for record in ordered:
        supports[record.category] = supports.get(record.category, 0) + 1
    offset = max(supports.values())
    # Equality at half the dataset is safe; a larger block cannot be
    # deranged against different categories.
    if offset > len(ordered) - offset:
        raise DataIntegrityError("A category is too large for an unrelated-pair derangement")
    mapping = {
        record.sample_id: ordered[(index + offset) % len(ordered)]
        for index, record in enumerate(ordered)
    }
    if len({donor.sample_id for donor in mapping.values()}) != len(ordered):
        raise DataIntegrityError("Unrelated-pair mapping is not bijective")
    if any(
        source.sample_id == mapping[source.sample_id].sample_id
        or source.category == mapping[source.sample_id].category
        for source in ordered
    ):
        raise DataIntegrityError("Unrelated-pair mapping retained a sample or category")
    return mapping


def _pair_for_condition(
    record: ManifestRecord,
    *,
    dataset_root: Path,
    condition: RobustnessCondition,
    unrelated: dict[str, ManifestRecord],
) -> tuple[Any, Any]:
    before_path = dataset_root / record.before_path
    after_path = dataset_root / record.after_path
    if condition.group == "clean":
        return before_path, after_path
    if condition.perturbation is not None:
        return perturb_pair(before_path, after_path, condition.perturbation)
    if condition.misuse == "same_before_image":
        return same_image_pair(before_path)
    if condition.misuse == "swapped_order":
        return swapped_pair(before_path, after_path)
    if condition.misuse == "unrelated_after":
        donor = unrelated[record.sample_id]
        return before_path, dataset_root / donor.after_path
    raise DataIntegrityError(f"Unsupported robustness condition: {condition.name}")


def _validate_quantiles(value: np.ndarray, expected_count: int) -> np.ndarray:
    quantiles = np.asarray(value, dtype=np.float32)
    if quantiles.shape != (expected_count, 3) or not np.isfinite(quantiles).all():
        raise DataIntegrityError(
            f"Robustness predictor must return finite [{expected_count}, 3] quantiles"
        )
    tolerance = 1e-5
    if (
        np.any(quantiles < -tolerance)
        or np.any(quantiles > 1.0 + tolerance)
        or np.any(quantiles[:, 0] > quantiles[:, 1] + tolerance)
        or np.any(quantiles[:, 1] > quantiles[:, 2] + tolerance)
    ):
        raise DataIntegrityError("Robustness prediction violated the ordered [0,1] contract")
    return np.clip(quantiles, 0.0, 1.0)


def _predict_condition(
    records: Sequence[ManifestRecord],
    *,
    dataset_root: Path,
    condition: RobustnessCondition,
    unrelated: dict[str, ManifestRecord],
    predictor: BatchPredictor,
    batch_size: int,
) -> np.ndarray:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    outputs: list[np.ndarray] = []
    for start in range(0, len(records), batch_size):
        before_values: list[np.ndarray] = []
        after_values: list[np.ndarray] = []
        for record in records[start : start + batch_size]:
            before, after = _pair_for_condition(
                record,
                dataset_root=dataset_root,
                condition=condition,
                unrelated=unrelated,
            )
            before_values.append(deterministic_preprocess(before))
            after_values.append(deterministic_preprocess(after))
        before_batch = np.stack(before_values).astype(np.float32, copy=False)
        after_batch = np.stack(after_values).astype(np.float32, copy=False)
        outputs.append(_validate_quantiles(predictor(before_batch, after_batch), len(before_batch)))
    return np.concatenate(outputs, axis=0)


def evaluate_frozen_robustness(
    *,
    artifact: FrozenFinalArtifact,
    dataset_root: str | Path,
    predictor: BatchPredictor,
    dataset_verification: dict[str, Any],
    batch_size: int = 32,
) -> dict[str, Any]:
    """Evaluate every preregistered condition and return deterministic evidence."""

    root = Path(dataset_root)
    if not root.is_dir():
        raise DataIntegrityError(f"Dataset root is missing: {root}")
    records = _validated_records(artifact.manifest_path)
    unrelated = unrelated_after_mapping(records)
    targets = np.asarray([record.leftover_fraction for record in records], dtype=np.float64)
    categories = np.asarray([record.category for record in records], dtype=str)
    condition_results: list[dict[str, Any]] = []
    clean_macro_mae: float | None = None

    for condition in FROZEN_CONDITIONS:
        quantiles = _predict_condition(
            records,
            dataset_root=root,
            condition=condition,
            unrelated=unrelated,
            predictor=predictor,
            batch_size=batch_size,
        )
        metrics = regression_metrics(targets, quantiles[:, 1], categories).to_dict()
        macro_mae = float(metrics["macro_category_mae"])
        if condition.group == "clean":
            clean_macro_mae = macro_mae
        if clean_macro_mae is None:
            raise DataIntegrityError("Clean robustness condition must be evaluated first")
        delta = macro_mae - clean_macro_mae
        prediction_rows = [
            {
                "sample_id": record.sample_id,
                "category": record.category,
                "target": record.leftover_fraction,
                "q05": float(row[0]),
                "q50": float(row[1]),
                "q95": float(row[2]),
            }
            for record, row in zip(records, quantiles, strict=True)
        ]
        routine = condition.group == "routine_perturbation"
        condition_results.append(
            {
                "name": condition.name,
                "group": condition.group,
                "mode": None if condition.perturbation is None else condition.perturbation.mode,
                "parameter": (
                    None if condition.perturbation is None else condition.perturbation.parameter
                ),
                "misuse_rule": condition.misuse,
                "n": len(prediction_rows),
                "category_count": 34,
                "macro_category_mae": macro_mae,
                "delta_macro_category_mae_from_clean": delta,
                "routine_downgrade_threshold": (
                    ROBUSTNESS_DOWNGRADE_THRESHOLD if routine else None
                ),
                "exceeds_routine_downgrade_threshold": (
                    delta > ROBUSTNESS_DOWNGRADE_THRESHOLD if routine else False
                ),
                "metrics": metrics,
                "predictions_sha256": canonical_json_sha256(prediction_rows),
                "predictions": prediction_rows,
            }
        )

    downgrade = any(
        bool(result["exceeds_routine_downgrade_threshold"])
        for result in condition_results
        if result["group"] == "routine_perturbation"
    )
    core: dict[str, Any] = {
        "schema_version": ROBUSTNESS_SCHEMA_VERSION,
        "kind": "frozen_final_model_robustness",
        "status": "complete",
        "model_identity": artifact.evidence_identity(),
        "dataset_verification": dataset_verification,
        "evaluation_contract": {
            "valid_pair_count": EXPECTED_VALID_PAIRS,
            "category_count": 34,
            "condition_count": len(FROZEN_CONDITIONS),
            "point_prediction": "raw_q50",
            "routine_downgrade_rule": "delta_macro_category_mae_from_clean > 0.03",
            "misuse_conditions_do_not_trigger_robustness_downgrade": True,
            "unrelated_pair_rule": (
                "category-sorted cyclic after-image rotation by maximum category support"
            ),
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "batch_size": batch_size,
        },
        "clean_macro_category_mae": clean_macro_mae,
        "robustness_downgrade_required": downgrade,
        "conditions": condition_results,
    }
    return core | {"evidence_sha256": canonical_json_sha256(core)}


def torch_batch_predictor(model: Any, *, device: str) -> BatchPredictor:
    """Wrap a loaded final Torch model in the model-free evaluator contract."""

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise missing_extra("Robustness inference", "train", "torch") from exc

    def predict(before: np.ndarray, after: np.ndarray) -> np.ndarray:
        with torch.inference_mode():
            output = model(
                torch.from_numpy(before).to(device),
                torch.from_numpy(after).to(device),
            )
        return np.asarray(output.detach().cpu().numpy(), dtype=np.float32)

    return predict


def write_robustness_evidence(path: str | Path, evidence: Mapping[str, Any]) -> None:
    """Write robustness evidence once, after verifying its embedded digest."""

    payload = dict(evidence)
    digest = payload.pop("evidence_sha256", None)
    if digest != canonical_json_sha256(payload):
        raise DataIntegrityError("Robustness evidence digest is missing or invalid")
    write_immutable_json(path, dict(evidence))
