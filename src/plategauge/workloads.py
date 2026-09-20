"""Executable workload implementations for orchestration task contracts.

Lightweight baselines run with core dependencies. Neural and frozen-embedding
references import Torch/timm lazily, verify exact pinned checkpoint bytes, and
fail closed when an artifact or optional dependency is absent.
"""

from __future__ import annotations

import csv
import importlib.metadata
import json
import os
import platform
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np

from .baselines import (
    PAIRING_MAP_FIELDS,
    RidgeRegressor,
    fixed_within_category_wrong_pairs,
    observer_leftover_reference,
    training_median_baseline,
)
from .data import sha256_file
from .errors import DataIntegrityError, missing_extra
from .evaluation import PREDICTION_FIELDS
from .features import extract_feature_matrix
from .metrics import macro_category_mae
from .model import (
    PairedQuantileRegressor,
    build_after_only_model,
    build_paired_model,
    configure_trainable_stages,
)
from .orchestration import TaskRequest, WorkloadResult
from .schema import ManifestRecord, read_manifest
from .training import (
    MODEL_CONFIGURATIONS,
    PairedImageDataset,
    fit_model,
    seed_everything,
)
from .uncertainty import correct_intervals, retention_mask


def _records_for_folds(records: list[ManifestRecord], folds: tuple[int, ...]) -> list[ManifestRecord]:
    selected = [record for record in records if record.is_valid and record.outer_fold in folds]
    return sorted(selected, key=lambda record: record.sample_id)


def _validate_scope(request: TaskRequest, records: list[ManifestRecord]) -> tuple[
    list[ManifestRecord], list[ManifestRecord]
]:
    task = request.task
    train = _records_for_folds(records, task.training_folds)
    evaluation = (
        []
        if task.evaluation_fold is None
        else _records_for_folds(records, (task.evaluation_fold,))
    )
    expected = task.expected_counts
    if "training_count" in expected and len(train) != expected["training_count"]:
        raise DataIntegrityError(
            f"Task {task.task_id} training scope has {len(train)} rows, expected "
            f"{expected['training_count']}"
        )
    if "prediction_count" in expected and len(evaluation) != expected["prediction_count"]:
        raise DataIntegrityError(
            f"Task {task.task_id} evaluation scope has {len(evaluation)} rows, expected "
            f"{expected['prediction_count']}"
        )
    return train, evaluation


def _write_predictions(
    path: Path,
    records: list[ManifestRecord],
    quantiles: np.ndarray,
    *,
    workload: str,
    configuration: str = "",
    epoch: int = 0,
) -> None:
    values = np.asarray(quantiles, dtype=np.float64)
    if values.shape != (len(records), 3) or not np.isfinite(values).all():
        raise DataIntegrityError("Prediction output must be finite [n,3] quantiles")
    if np.any(values < 0) or np.any(values > 1) or np.any(np.diff(values, axis=1) < 0):
        raise DataIntegrityError("Prediction quantiles must be ordered in [0,1]")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTION_FIELDS, lineterminator="\n")
        writer.writeheader()
        for record, prediction in zip(records, values, strict=True):
            writer.writerow(
                {
                    "sample_id": record.sample_id,
                    "category": record.category,
                    "outer_fold": record.outer_fold,
                    "target": format(record.leftover_fraction, ".17g"),
                    "q05": format(float(prediction[0]), ".17g"),
                    "q50": format(float(prediction[1]), ".17g"),
                    "q95": format(float(prediction[2]), ".17g"),
                    "workload": workload,
                    "configuration": configuration,
                    "epoch": epoch,
                }
            )


def _point_quantiles(predictions: np.ndarray) -> np.ndarray:
    points = np.clip(np.asarray(predictions, dtype=np.float64).reshape(-1), 0.0, 1.0)
    return np.repeat(points[:, None], 3, axis=1)


def _prediction_payload(
    task_expected: dict[str, int], records: list[ManifestRecord], quantiles: np.ndarray
) -> dict[str, Any]:
    payload: dict[str, Any] = dict(task_expected)
    if records:
        payload["macro_category_mae"] = macro_category_mae(
            np.asarray([record.leftover_fraction for record in records]),
            np.asarray(quantiles)[:, 1],
            np.asarray([record.category for record in records]),
        )
    return payload


def _extract_handcrafted(records: list[ManifestRecord], root: Path) -> np.ndarray:
    return extract_feature_matrix(
        [(root / record.before_path, root / record.after_path) for record in records]
    )


def _ridge_fold_scores(
    features: np.ndarray,
    records: list[ManifestRecord],
    folds: tuple[int, ...],
    alphas: tuple[float, ...],
) -> tuple[dict[str, dict[str, float]], list[dict[str, Any]]]:
    targets = np.asarray([record.leftover_fraction for record in records], dtype=np.float64)
    categories = np.asarray([record.category for record in records])
    record_folds = np.asarray([record.outer_fold for record in records])
    scores: dict[str, dict[str, float]] = {}
    rows: list[dict[str, Any]] = []
    for alpha in alphas:
        alpha_key = format(alpha, "g")
        scores[alpha_key] = {}
        for fold in folds:
            validation = record_folds == fold
            training = ~validation
            model = RidgeRegressor(alpha=alpha).fit(features[training], targets[training])
            predictions = model.predict(features[validation])
            score = macro_category_mae(
                targets[validation], predictions, categories[validation]
            )
            scores[alpha_key][str(fold)] = score
            for record, prediction in zip(
                np.asarray(records, dtype=object)[validation], predictions, strict=True
            ):
                rows.append(
                    {
                        "alpha": alpha_key,
                        "validation_fold": fold,
                        "sample_id": record.sample_id,
                        "target": record.leftover_fraction,
                        "prediction": float(prediction),
                    }
                )
    return scores, rows


def _write_oof_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ("alpha", "validation_fold", "sample_id", "target", "prediction")
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {
                key: format(value, ".17g") if isinstance(value, float) else value
                for key, value in row.items()
            }
            for row in rows
        )


def _execute_median_or_observer(
    request: TaskRequest,
    workspace: Path,
    train: list[ManifestRecord],
    evaluation: list[ManifestRecord],
) -> WorkloadResult:
    if request.task.workload == "training_median":
        predictions = training_median_baseline(
            np.asarray([record.leftover_fraction for record in train]), len(evaluation)
        )
    else:
        predictions = observer_leftover_reference(
            np.asarray([record.observer_score for record in evaluation])
        )
    quantiles = _point_quantiles(predictions)
    artifact = workspace / "predictions.csv"
    _write_predictions(
        artifact, evaluation, quantiles, workload=request.task.workload
    )
    return WorkloadResult(
        payload=_prediction_payload(request.task.expected_counts, evaluation, quantiles),
        artifacts={"predictions": artifact.name},
    )


def _execute_handcrafted(
    request: TaskRequest,
    workspace: Path,
    root: Path,
    train: list[ManifestRecord],
    evaluation: list[ManifestRecord],
    all_records: list[ManifestRecord],
) -> WorkloadResult:
    task = request.task
    if task.stage == "inner_tuning":
        development = _records_for_folds(all_records, task.training_folds)
        if len(development) != task.expected_counts["development_count"]:
            raise DataIntegrityError("Handcrafted tuning development count changed")
        features = _extract_handcrafted(development, root)
        alphas = tuple(float(value) for value in task.parameters["alphas"])
        scores, rows = _ridge_fold_scores(features, development, task.validation_folds, alphas)
        artifact = workspace / "oof_predictions.csv"
        _write_oof_rows(artifact, rows)
        return WorkloadResult(
            payload={**task.expected_counts, "fold_scores": scores},
            artifacts={"oof_predictions": artifact.name},
        )
    alpha = float(task.parameters["alpha"])
    train_features = _extract_handcrafted(train, root)
    evaluation_features = _extract_handcrafted(evaluation, root)
    model = RidgeRegressor(alpha=alpha).fit(
        train_features,
        np.asarray([record.leftover_fraction for record in train]),
    )
    quantiles = _point_quantiles(model.predict(evaluation_features))
    artifact = workspace / "predictions.csv"
    _write_predictions(artifact, evaluation, quantiles, workload=task.workload)
    return WorkloadResult(
        payload=_prediction_payload(task.expected_counts, evaluation, quantiles),
        artifacts={"predictions": artifact.name},
    )


def _verify_checkpoint(metadata: dict[str, Any], checkpoint_root: Path) -> Path:
    required = ("checkpoint", "revision", "filename", "size_bytes", "sha256")
    if any(name not in metadata for name in required):
        raise DataIntegrityError("Task lacks complete pinned checkpoint metadata")
    path = (
        checkpoint_root
        / str(metadata["checkpoint"])
        / str(metadata["revision"])
        / str(metadata["filename"])
    )
    if not path.is_file():
        raise DataIntegrityError(f"Pinned checkpoint is missing: {path}")
    if path.stat().st_size != int(metadata["size_bytes"]):
        raise DataIntegrityError(f"Pinned checkpoint size mismatch: {path}")
    if sha256_file(path) != str(metadata["sha256"]):
        raise DataIntegrityError(f"Pinned checkpoint SHA-256 mismatch: {path}")
    return path


def _require_torch() -> tuple[Any, Any]:  # pragma: no cover - optional heavy runtime
    try:
        import torch
        from torch.utils.data import DataLoader
    except ImportError as exc:
        raise missing_extra("Experiment workload", "train", "torch") from exc
    return torch, DataLoader


def _build_reference_encoder(
    metadata: dict[str, Any], checkpoint_root: Path
) -> tuple[Any, int]:  # pragma: no cover - optional heavy runtime
    try:
        import timm
    except ImportError as exc:
        raise missing_extra("Reference encoder", "train", "timm") from exc
    checkpoint = _verify_checkpoint(metadata, checkpoint_root)
    encoder = timm.create_model(
        str(metadata["checkpoint"]),
        pretrained=False,
        checkpoint_path=str(checkpoint),
    )
    reset_classifier = getattr(encoder, "reset_classifier", None)
    if not callable(reset_classifier):
        raise DataIntegrityError("Reference encoder cannot remove its classifier safely")
    reset_classifier(0, global_pool="avg")
    feature_dimension = int(cast(Any, encoder).num_features)
    return encoder, feature_dimension


def _model_forward(model: Any, batch: dict[str, Any], after_only: bool) -> Any:
    return model(batch["after"]) if after_only else model(batch["before"], batch["after"])


def _final_encoder_stages(encoder: Any) -> list[Any]:
    stages = getattr(encoder, "blocks", None) or getattr(encoder, "features", None)
    if stages is not None:
        stage_list = list(stages.children())
    else:
        stage_list = [
            getattr(encoder, name, None) for name in ("layer1", "layer2", "layer3", "layer4")
        ]
        if not all(stage is not None for stage in stage_list):
            raise DataIntegrityError("Encoder exposes no approved trainable-stage structure")
    if len(stage_list) < 2:
        raise DataIntegrityError("Encoder exposes fewer than two trainable stages")
    return stage_list[-2:]


def _fit_fixed_epochs(
    model: Any,
    loader: Any,
    configuration_name: str,
    parameters: dict[str, Any],
    *,
    device: str,
    after_only: bool,
) -> None:  # pragma: no cover - optional heavy runtime
    torch, _ = _require_torch()
    configuration = MODEL_CONFIGURATIONS[configuration_name]
    epochs = int(parameters["epoch"])
    freeze_epochs = int(parameters["freeze_encoder_epochs"])
    seed_everything(int(parameters["seed"]))
    target_device = torch.device(device)
    model.to(target_device)
    configure_trainable_stages(model, encoder_frozen=True)
    from .model import QuantileRegressionLoss

    criterion = QuantileRegressionLoss(interval_weight=float(parameters["interval_loss_weight"]))

    def optimizer() -> Any:
        groups = [{"params": model.head.parameters(), "lr": configuration.head_learning_rate}]
        encoder_parameters = [
            value for value in model.encoder.parameters() if value.requires_grad
        ]
        if encoder_parameters:
            groups.append({"params": encoder_parameters, "lr": configuration.encoder_learning_rate})
        return torch.optim.AdamW(groups, weight_decay=float(parameters["weight_decay"]))

    current_optimizer = optimizer()
    use_amp = target_device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    encoder_frozen = True
    for epoch in range(1, epochs + 1):
        if epoch == freeze_epochs + 1:
            encoder_frozen = False
            configure_trainable_stages(model, encoder_frozen=False)
            current_optimizer = optimizer()
        model.train()
        # Preserve the same frozen-stage BatchNorm policy as inner training.
        model.encoder.eval()
        if not encoder_frozen:
            for stage in _final_encoder_stages(model.encoder):
                stage.train()
        for batch in loader:
            moved = {
                **batch,
                "before": batch["before"].to(target_device),
                "after": batch["after"].to(target_device),
            }
            targets = batch["target"].to(target_device)
            current_optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(target_device.type, enabled=use_amp):
                prediction = _model_forward(model, moved, after_only)
                loss = criterion(prediction, targets)
            scaler.scale(loss).backward()
            scaler.unscale_(current_optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), float(parameters["gradient_clip"]))
            scaler.step(current_optimizer)
            scaler.update()


def _predict_neural(
    model: Any, loader: Any, *, device: str, after_only: bool
) -> tuple[list[str], np.ndarray]:  # pragma: no cover - optional heavy runtime
    torch, _ = _require_torch()
    model.eval()
    target_device = torch.device(device)
    sample_ids: list[str] = []
    outputs: list[np.ndarray] = []
    with torch.inference_mode():
        for batch in loader:
            moved = {
                **batch,
                "before": batch["before"].to(target_device),
                "after": batch["after"].to(target_device),
            }
            prediction = _model_forward(model, moved, after_only)
            outputs.append(prediction.detach().cpu().numpy())
            sample_ids.extend(str(value) for value in batch["sample_id"])
    return sample_ids, np.concatenate(outputs, axis=0)


def _wrong_pair_records(
    records: list[ManifestRecord], *, scope: str
) -> tuple[list[ManifestRecord], list[dict[str, str]], tuple[str, ...]]:
    if scope not in {"training", "evaluation"}:
        raise DataIntegrityError("Wrong-pair scope must be training or evaluation")
    try:
        control = fixed_within_category_wrong_pairs(records)
    except ValueError as exc:
        raise DataIntegrityError(str(exc)) from exc
    by_id = {record.sample_id: record for record in records}
    paired = []
    for record in records:
        donor = by_id[control.source_sample_by_sample[record.sample_id]]
        paired.append(
            replace(
                record,
                after_path=donor.after_path,
                after_width=donor.after_width,
                after_height=donor.after_height,
                after_sha256=donor.after_sha256,
            )
        )
    if len(paired) != len(records):  # pragma: no cover - defensive mapping invariant
        raise DataIntegrityError("Wrong-pair control must preserve every record")
    rows = [
        {
            "sample_id": record.sample_id,
            "original_after_path": record.after_path,
            "wrong_after_path": control.after_path_by_sample[record.sample_id],
            "source_sample_id": control.source_sample_by_sample[record.sample_id],
            "rule": control.rule_by_sample[record.sample_id],
            "scope": scope,
        }
        for record in sorted(records, key=lambda value: value.sample_id)
    ]
    fallback_ids = tuple(
        sorted(
            row["sample_id"]
            for row in rows
            if row["rule"].startswith("same_fold_singleton_swap")
        )
    )
    if set(row["source_sample_id"] for row in rows) != set(by_id):
        raise DataIntegrityError("Wrong-pair control is not a complete after-image bijection")
    return paired, rows, fallback_ids


def _write_pairing_map(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIRING_MAP_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _build_neural_model(task: Any, checkpoint_root: Path) -> tuple[Any, bool, str]:
    """Seed before constructing every random head, then load only pinned weights."""

    parameters = task.parameters
    configuration_name = str(parameters["configuration"])
    if configuration_name not in MODEL_CONFIGURATIONS:
        raise DataIntegrityError(f"Unknown neural configuration {configuration_name!r}")
    seed_everything(int(parameters["seed"]))
    after_only = task.workload == "after_only_mobilenet"
    metadata = parameters["pretrained_artifact"]
    if not isinstance(metadata, dict):
        raise DataIntegrityError("Neural task lacks pretrained artifact metadata")
    weights = _verify_checkpoint(metadata, checkpoint_root)
    if task.workload == "paired_resnet50":
        encoder, feature_dimension = _build_reference_encoder(metadata, checkpoint_root)
        model = PairedQuantileRegressor(
            encoder, feature_dimension, dropout=float(parameters["dropout"])
        )
    elif after_only:
        model = build_after_only_model(
            dropout=float(parameters["dropout"]), pretrained=True, weights_path=weights
        )
    else:
        model = build_paired_model(
            dropout=float(parameters["dropout"]), pretrained=True, weights_path=weights
        )
    return model, after_only, configuration_name


def _execute_neural(
    request: TaskRequest,
    workspace: Path,
    checkpoint_root: Path,
    root: Path,
    train: list[ManifestRecord],
    evaluation: list[ManifestRecord],
    all_records: list[ManifestRecord],
    device: str,
) -> WorkloadResult:  # pragma: no cover - optional heavy runtime
    torch, DataLoader = _require_torch()
    task = request.task
    parameters = task.parameters
    batch_size = int(parameters["batch_size"])
    if task.stage == "inner_primary":
        train = _records_for_folds(all_records, task.training_folds)
        evaluation = _records_for_folds(all_records, task.validation_folds)
        if len(train) != task.expected_counts["training_count"] or len(evaluation) != task.expected_counts[
            "validation_count"
        ]:
            raise DataIntegrityError("Inner neural scope counts changed")
    fallback_ids: tuple[str, ...] = ()
    pairing_rows: list[dict[str, str]] = []
    if task.workload == "fixed_within_category_wrong_pair":
        train, train_rows, train_fallback = _wrong_pair_records(train, scope="training")
        evaluation, evaluation_rows, evaluation_fallback = _wrong_pair_records(
            evaluation, scope="evaluation"
        )
        pairing_rows = [*train_rows, *evaluation_rows]
        fallback_ids = tuple(sorted((*train_fallback, *evaluation_fallback)))

    model, after_only, configuration_name = _build_neural_model(task, checkpoint_root)
    train_dataset = PairedImageDataset(
        train, root, training=True, seed=int(parameters["seed"])
    )
    evaluation_dataset = PairedImageDataset(
        evaluation, root, training=False, seed=int(parameters["seed"])
    )
    generator = torch.Generator().manual_seed(int(parameters["seed"]))
    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=0, generator=generator
    )
    evaluation_loader = DataLoader(
        evaluation_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )
    if task.stage == "inner_primary":
        fit = fit_model(
            model,
            train_loader,
            evaluation_loader,
            MODEL_CONFIGURATIONS[configuration_name],
            device=device,
            maximum_epochs=int(parameters["maximum_epochs"]),
            patience=int(parameters["patience"]),
            freeze_epochs=int(parameters["freeze_encoder_epochs"]),
            weight_decay=float(parameters["weight_decay"]),
            gradient_clip=float(parameters["gradient_clip"]),
            interval_weight=float(parameters["interval_loss_weight"]),
            seed=int(parameters["seed"]),
        )
        model.load_state_dict(fit.state_dict)
        checkpoint = workspace / "checkpoint.pt"
        torch.save({"state_dict": fit.state_dict, "task_id": task.task_id}, checkpoint)
        _, quantiles = _predict_neural(model, evaluation_loader, device=device, after_only=False)
        predictions = workspace / "validation_predictions.csv"
        _write_predictions(
            predictions,
            evaluation,
            quantiles,
            workload=task.workload,
            configuration=configuration_name,
            epoch=fit.best_epoch,
        )
        # The training loader exposes float32 targets for optimization, while the
        # immutable manifest and prediction artifact retain the recorded target
        # at full precision.  Publish the selection metric from the canonical
        # artifact domain so strict replay produces the identical value.
        prediction_payload = _prediction_payload(task.expected_counts, evaluation, quantiles)
        return WorkloadResult(
            payload={
                **prediction_payload,
                "best_epoch": fit.best_epoch,
            },
            artifacts={
                "checkpoint": checkpoint.name,
                "validation_predictions": predictions.name,
            },
        )

    _fit_fixed_epochs(
        model,
        train_loader,
        configuration_name,
        parameters,
        device=device,
        after_only=after_only,
    )
    if task.stage == "final":
        checkpoint = workspace / "model_checkpoint.pt"
        torch.save({"state_dict": model.state_dict(), "task_id": task.task_id}, checkpoint)
        return WorkloadResult(
            payload=dict(task.expected_counts), artifacts={"model_checkpoint": checkpoint.name}
        )
    sample_ids, quantiles = _predict_neural(
        model, evaluation_loader, device=device, after_only=after_only
    )
    expected_ids = [record.sample_id for record in evaluation]
    if sample_ids != expected_ids:
        raise DataIntegrityError("Neural prediction order differs from deterministic evaluation order")
    policy = parameters.get("uncertainty_policy")
    retained: np.ndarray | None = None
    if task.workload == "paired_mobilenet":
        if not isinstance(policy, dict):
            raise DataIntegrityError(
                "Outer primary task lacks its frozen inner-only uncertainty policy"
            )
        correction = float(policy["interval_correction"])
        threshold = float(policy["abstention_threshold"])
        corrected_lower, corrected_upper = correct_intervals(
            quantiles[:, 0], quantiles[:, 2], correction
        )
        quantiles = np.asarray(quantiles, dtype=np.float64).copy()
        quantiles[:, 0] = corrected_lower
        quantiles[:, 2] = corrected_upper
        retained = retention_mask(corrected_lower, corrected_upper, threshold)
    predictions = workspace / "predictions.csv"
    _write_predictions(
        predictions,
        evaluation,
        quantiles,
        workload=task.workload,
        configuration=configuration_name,
        epoch=int(parameters["epoch"]),
    )
    payload = _prediction_payload(task.expected_counts, evaluation, quantiles)
    if retained is not None:
        assert isinstance(policy, dict)
        payload |= {
            "interval_correction": float(policy["interval_correction"]),
            "abstention_threshold": float(policy["abstention_threshold"]),
            "retained_count": int(np.sum(retained)),
            "retained_sample_ids": [
                sample_id for sample_id, keep in zip(sample_ids, retained, strict=True) if keep
            ],
        }
    artifacts = {"predictions": predictions.name}
    if task.workload == "fixed_within_category_wrong_pair":
        pairing_map = workspace / "pairing_map.csv"
        _write_pairing_map(pairing_map, pairing_rows)
        artifacts["pairing_map"] = pairing_map.name
        payload |= {
            "singleton_fallback_count": len(fallback_ids),
            "singleton_fallback_sample_ids": list(fallback_ids),
        }
    return WorkloadResult(
        payload=payload,
        artifacts=artifacts,
    )


def _build_dino_cache_identity(
    *,
    checkpoint_sha256: str,
    manifest_sha256: str,
    versions: dict[str, str],
    hardware: dict[str, Any],
    determinism: dict[str, Any],
    embedding_batch_size: int,
    preprocessing: dict[str, Any],
    implementation_sha256: str,
) -> dict[str, Any]:
    """Build the complete content-independent identity for cached DINO features."""

    if embedding_batch_size < 1:
        raise DataIntegrityError("DINO embedding batch size must be positive")
    preprocessing_sha = sha256_file_bytes(
        json.dumps(preprocessing, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return {
        "checkpoint_sha256": checkpoint_sha256,
        "manifest_sha256": manifest_sha256,
        "versions": dict(sorted(versions.items())),
        "hardware": hardware,
        "determinism": determinism,
        "embedding_batch_size": embedding_batch_size,
        "preprocessing": preprocessing,
        "preprocessing_sha256": preprocessing_sha,
        "implementation_sha256": implementation_sha256,
    }


def _validate_dino_feature_arrays(
    *,
    expected_ids: list[str],
    observed_ids: list[str],
    features: np.ndarray,
    recorded_identity_sha256: str,
    expected_identity_sha256: str,
    recorded_features_sha256: str,
) -> str:
    """Validate the fixed 514x1,536 feature tensor and return its content hash."""

    matrix = np.asarray(features, dtype=np.float32)
    features_sha = sha256_file_bytes(matrix.tobytes(order="C"))
    if (
        len(expected_ids) != 514
        or observed_ids != expected_ids
        or matrix.shape != (514, 1536)
        or not np.isfinite(matrix).all()
        or recorded_identity_sha256 != expected_identity_sha256
        or recorded_features_sha256 != features_sha
    ):
        raise DataIntegrityError("DINO feature cache identity, shape, or contents are invalid")
    return features_sha


def _cuda_device_index(torch_module: Any, device: str) -> int:
    parsed = torch_module.device(device)
    if str(parsed.type) != "cuda":
        raise DataIntegrityError("CUDA device metadata requested for a non-CUDA device")
    return int(parsed.index) if parsed.index is not None else int(torch_module.cuda.current_device())


def _dino_feature_cache(
    records: list[ManifestRecord],
    root: Path,
    metadata: dict[str, Any],
    checkpoint_root: Path,
    cache_root: Path,
    manifest_hash: str,
    device: str,
    batch_size: int,
    seed: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:  # pragma: no cover - optional heavy runtime
    torch, _ = _require_torch()
    try:
        import timm
        from PIL import Image
    except ImportError as exc:
        raise missing_extra("DINO feature extraction", "train", "timm/Pillow") from exc
    if len(records) != 514:
        raise DataIntegrityError("Pinned DINO cache requires all 514 valid pairs")
    weights = _verify_checkpoint(metadata, checkpoint_root)
    encoder, _ = _build_reference_encoder(metadata, checkpoint_root)
    timm_data = cast(Any, timm.data)
    config = timm_data.resolve_model_data_config(encoder)
    if tuple(config.get("input_size", ())) != (3, 518, 518):
        raise DataIntegrityError("Pinned DINO model no longer declares native 518x518 input")
    preprocessing_identity = {
        "input_size": list(config["input_size"]),
        "interpolation": str(config.get("interpolation")),
        "mean": list(config.get("mean", ())),
        "std": list(config.get("std", ())),
        "crop_pct": float(config.get("crop_pct", 1.0)),
        "crop_mode": str(config.get("crop_mode", "center")),
    }
    parsed_device = torch.device(device)
    device_type = str(parsed_device.type)
    hardware: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "device_type": device_type,
    }
    if device_type == "cuda":
        device_index = _cuda_device_index(torch, device)
        hardware |= {
            "cuda_device_name": torch.cuda.get_device_name(device_index),
            "cuda_capability": list(torch.cuda.get_device_capability(device_index)),
        }
    cache_identity = _build_dino_cache_identity(
        checkpoint_sha256=sha256_file(weights),
        manifest_sha256=manifest_hash,
        versions={
            "timm": importlib.metadata.version("timm"),
            "torch": str(torch.__version__),
            "torchvision": importlib.metadata.version("torchvision"),
            "numpy": str(np.__version__),
            "Pillow": importlib.metadata.version("Pillow"),
            "cuda": str(torch.version.cuda),
            "cudnn": str(torch.backends.cudnn.version()),
        },
        hardware=hardware,
        determinism={
            "seed": seed,
            "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
            "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
            "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
            "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        },
        embedding_batch_size=batch_size,
        preprocessing=preprocessing_identity,
        implementation_sha256=sha256_file(Path(__file__)),
    )
    cache_identity_sha = sha256_file_bytes(
        json.dumps(cache_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = cache_root / f"dinov2-paired-{cache_identity_sha}.npz"
    metadata_path = cache_root / f"dinov2-paired-{cache_identity_sha}.json"
    if cache_path.exists() != metadata_path.exists():
        raise DataIntegrityError("DINO feature cache archive/metadata pair is incomplete")
    if cache_path.is_file():
        try:
            cache_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataIntegrityError("DINO feature cache metadata is unreadable") from exc
        if (
            not isinstance(cache_metadata, dict)
            or cache_metadata.get("cache_identity") != cache_identity
            or cache_metadata.get("cache_identity_sha256") != cache_identity_sha
            or cache_metadata.get("archive_sha256") != sha256_file(cache_path)
        ):
            raise DataIntegrityError("DINO feature cache metadata or archive hash is invalid")
        with np.load(cache_path, allow_pickle=False) as cached:
            ids = [str(value) for value in cached["sample_ids"]]
            features = np.asarray(cached["features"], dtype=np.float32)
            recorded_identity = str(cached["cache_identity_sha256"].item())
            recorded_features_hash = str(cached["features_sha256"].item())
        features_hash = _validate_dino_feature_arrays(
            expected_ids=[record.sample_id for record in records],
            observed_ids=ids,
            features=features,
            recorded_identity_sha256=recorded_identity,
            expected_identity_sha256=cache_identity_sha,
            recorded_features_sha256=recorded_features_hash,
        )
        if (
            cache_metadata.get("features_sha256") != features_hash
            or cache_metadata.get("sample_ids_sha256")
            != sha256_file_bytes("\n".join(ids).encode("utf-8"))
        ):
            raise DataIntegrityError("DINO feature cache identity, shape, or contents are invalid")
        return (
            {sample_id: features[index] for index, sample_id in enumerate(ids)},
            cache_metadata,
        )

    transform = timm_data.create_transform(**config, is_training=False)
    encoder.to(torch.device(device)).eval()
    paired: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            before_tensors: list[Any] = []
            after_tensors: list[Any] = []
            for record in batch:
                with Image.open(root / record.before_path) as image:
                    before_tensors.append(transform(image.convert("RGB")))
                with Image.open(root / record.after_path) as image:
                    after_tensors.append(transform(image.convert("RGB")))
            before_batch = torch.stack(before_tensors).to(device)
            after_batch = torch.stack(after_tensors).to(device)
            before_features = encoder(before_batch).detach().cpu().numpy()
            after_features = encoder(after_batch).detach().cpu().numpy()
            fused = np.concatenate(
                (
                    before_features,
                    after_features,
                    np.abs(before_features - after_features),
                    before_features * after_features,
                ),
                axis=1,
            ).astype(np.float32)
            paired.extend(
                fused[index] for index in range(len(batch))
            )
    feature_matrix = np.stack(paired)
    if feature_matrix.shape != (514, 1536) or not np.isfinite(feature_matrix).all():
        raise DataIntegrityError("Pinned DINO paired features must have shape [514, 1536]")
    features_hash = sha256_file_bytes(feature_matrix.tobytes(order="C"))
    sample_ids_hash = sha256_file_bytes(
        "\n".join(record.sample_id for record in records).encode("utf-8")
    )
    try:
        with cache_path.open("xb") as handle:
            np.savez_compressed(
                handle,
                sample_ids=np.asarray([record.sample_id for record in records]),
                features=feature_matrix,
                cache_identity_sha256=np.asarray(cache_identity_sha),
                features_sha256=np.asarray(features_hash),
            )
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise DataIntegrityError("DINO feature cache appeared concurrently") from exc
    cache_metadata = {
        "cache_identity": cache_identity,
        "cache_identity_sha256": cache_identity_sha,
        "archive_filename": cache_path.name,
        "archive_sha256": sha256_file(cache_path),
        "features_sha256": features_hash,
        "sample_ids_sha256": sample_ids_hash,
        "shape": [514, 1536],
    }
    try:
        with metadata_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(cache_metadata, sort_keys=True, separators=(",", ":")) + "\n"
            )
    except FileExistsError as exc:
        raise DataIntegrityError("DINO feature cache metadata appeared concurrently") from exc
    return (
        {record.sample_id: feature_matrix[index] for index, record in enumerate(records)},
        cache_metadata,
    )


def _execute_dino(
    request: TaskRequest,
    workspace: Path,
    root: Path,
    checkpoint_root: Path,
    cache_root: Path,
    train: list[ManifestRecord],
    evaluation: list[ManifestRecord],
    all_records: list[ManifestRecord],
    device: str,
) -> WorkloadResult:  # pragma: no cover - optional heavy runtime
    task = request.task
    seed = int(task.parameters["seed"])
    seed_everything(seed)
    metadata = task.parameters["pretrained_artifact"]
    if not isinstance(metadata, dict):
        raise DataIntegrityError("DINO task lacks pinned artifact metadata")
    valid = sorted((record for record in all_records if record.is_valid), key=lambda row: row.sample_id)
    batch_size = int(
        task.parameters[
            "embedding_batch_size_cuda" if str(device).startswith("cuda") else "embedding_batch_size_cpu"
        ]
    )
    features_by_id, cache_metadata = _dino_feature_cache(
        valid,
        root,
        metadata,
        checkpoint_root,
        cache_root,
        sha256_file(request.manifest_path),
        device,
        batch_size,
        seed,
    )
    if task.stage == "inner_tuning":
        development = _records_for_folds(all_records, task.training_folds)
        matrix = np.stack([features_by_id[record.sample_id] for record in development])
        alphas = tuple(float(value) for value in task.parameters["alphas"])
        scores, rows = _ridge_fold_scores(matrix, development, task.validation_folds, alphas)
        artifact = workspace / "oof_predictions.csv"
        _write_oof_rows(artifact, rows)
        return WorkloadResult(
            payload={
                **task.expected_counts,
                "fold_scores": scores,
                "feature_cache": cache_metadata,
            },
            artifacts={"oof_predictions": artifact.name},
        )
    train_matrix = np.stack([features_by_id[record.sample_id] for record in train])
    eval_matrix = np.stack([features_by_id[record.sample_id] for record in evaluation])
    model = RidgeRegressor(alpha=float(task.parameters["alpha"])).fit(
        train_matrix, np.asarray([record.leftover_fraction for record in train])
    )
    quantiles = _point_quantiles(model.predict(eval_matrix))
    artifact = workspace / "predictions.csv"
    _write_predictions(artifact, evaluation, quantiles, workload=task.workload)
    return WorkloadResult(
        payload={
            **_prediction_payload(task.expected_counts, evaluation, quantiles),
            "feature_cache": cache_metadata,
        },
        artifacts={"predictions": artifact.name},
    )


def execute_workload(
    request: TaskRequest,
    workspace: Path,
    *,
    checkpoint_root: Path,
    cache_root: Path,
    device: str,
) -> WorkloadResult:
    """Dispatch one fully scoped task to its concrete approved workload."""

    records = read_manifest(request.manifest_path)
    root = Path(request.dataset_root)
    train, evaluation = _validate_scope(request, records)
    workload = request.task.workload
    if workload in {"training_median", "observer_score_context_only"}:
        return _execute_median_or_observer(request, workspace, train, evaluation)
    if workload == "handcrafted_ridge":
        return _execute_handcrafted(request, workspace, root, train, evaluation, records)
    if workload == "frozen_paired_dinov2":
        return _execute_dino(
            request,
            workspace,
            root,
            checkpoint_root,
            cache_root,
            train,
            evaluation,
            records,
            device,
        )
    if workload in {
        "paired_mobilenet",
        "after_only_mobilenet",
        "fixed_within_category_wrong_pair",
        "paired_resnet50",
    }:
        return _execute_neural(
            request,
            workspace,
            checkpoint_root,
            root,
            train,
            evaluation,
            records,
            device,
        )
    raise DataIntegrityError(f"No approved workload implementation for {workload!r}")


class ProductionTaskRunner:
    """In-repository runner for real, pinned experiment workloads."""

    def __init__(
        self,
        *,
        checkpoint_root: str | Path = "artifacts/checkpoints",
        cache_root: str | Path = "artifacts/cache",
        device: str = "auto",
    ) -> None:
        self.checkpoint_root = Path(checkpoint_root)
        self.cache_root = Path(cache_root)
        self.device = self._resolve_device(device)
        cublas_workspace_config = self._validate_cuda_determinism_environment(self.device)
        source_paths = [
            Path(__file__).with_name(name)
            for name in (
                "workloads.py",
                "orchestration.py",
                "model.py",
                "training.py",
                "transforms.py",
                "features.py",
                "baselines.py",
                "metrics.py",
                "evaluation.py",
                "uncertainty.py",
                "schema.py",
                "data.py",
                "folds.py",
                "errors.py",
            )
        ]
        versions = {
            name: self._package_version(name)
            for name in ("numpy", "Pillow", "torch", "torchvision", "timm")
        }
        runtime: dict[str, Any] = {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "device": self.device,
            "cublas_workspace_config": cublas_workspace_config,
            "versions": versions,
        }
        try:
            import torch
        except ImportError:
            runtime["torch_runtime"] = None
        else:
            torch_runtime: dict[str, Any] = {
                "cuda_runtime": str(torch.version.cuda),
                "cudnn": str(cast(Any, torch.backends.cudnn).version()),
                "cuda_available": bool(torch.cuda.is_available()),
                "num_threads": int(torch.get_num_threads()),
                "num_interop_threads": int(torch.get_num_interop_threads()),
                "thread_environment": {
                    name: os.environ.get(name)
                    for name in (
                        "OMP_NUM_THREADS",
                        "MKL_NUM_THREADS",
                        "OPENBLAS_NUM_THREADS",
                    )
                },
            }
            if self.device.startswith("cuda") and torch.cuda.is_available():
                device_index = _cuda_device_index(torch, self.device)
                torch_runtime |= {
                    "device_name": torch.cuda.get_device_name(device_index),
                    "device_capability": list(torch.cuda.get_device_capability(device_index)),
                }
            runtime["torch_runtime"] = torch_runtime
        identity = {
            "runner": "PlateGaugeProductionTaskRunner/v1",
            "sources": {path.name: sha256_file(path) for path in source_paths},
            "runtime": runtime,
        }
        self._environment = identity
        self._fingerprint = sha256_file_bytes(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )

    @staticmethod
    def _package_version(name: str) -> str | None:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch
        except ImportError:
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    @staticmethod
    def _validate_cuda_determinism_environment(device: str) -> str | None:
        if not device.startswith("cuda"):
            return None
        value = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
        if value not in {":4096:8", ":16:8"}:
            raise DataIntegrityError(
                "CUDA confirmatory execution requires CUBLAS_WORKSPACE_CONFIG=:4096:8 "
                "(or :16:8) before starting Python; set it and launch a fresh process"
            )
        return value

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def environment(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(self._environment)))

    def execute(self, request: TaskRequest, workspace: Path) -> WorkloadResult:
        return execute_workload(
            request,
            workspace,
            checkpoint_root=self.checkpoint_root,
            cache_root=self.cache_root,
            device=self.device,
        )


def sha256_file_bytes(value: bytes) -> str:
    """Hash a small in-memory runner identity without creating a temporary file."""

    import hashlib

    return hashlib.sha256(value).hexdigest()
