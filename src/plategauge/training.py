"""Training primitives and deterministic nested-selection rules."""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .errors import missing_extra
from .metrics import macro_category_mae
from .model import QuantileRegressionLoss, configure_trainable_stages, torch_available
from .schema import ManifestRecord
from .transforms import PairedTrainTransform, deterministic_preprocess

SEED = 20260919


@dataclass(frozen=True, slots=True)
class ModelConfiguration:
    name: str
    encoder_learning_rate: float
    head_learning_rate: float
    dropout: float


MODEL_CONFIGURATIONS: dict[str, ModelConfiguration] = {
    "M1": ModelConfiguration("M1", 3e-5, 3e-4, 0.2),
    "M2": ModelConfiguration("M2", 1e-4, 1e-3, 0.4),
}


@dataclass(frozen=True, slots=True)
class InnerRun:
    configuration: str
    fold: int
    best_epoch: int
    macro_category_mae: float


@dataclass(frozen=True, slots=True)
class SelectedConfiguration:
    configuration: str
    epoch: int
    mean_macro_category_mae: float


def select_inner_configuration(runs: list[InnerRun]) -> SelectedConfiguration:
    """Select by mean inner macro-MAE; exact ties choose M1."""

    if not runs:
        raise ValueError("At least one inner run is required")
    grouped: dict[str, list[InnerRun]] = {}
    for run in runs:
        if run.configuration not in MODEL_CONFIGURATIONS:
            raise ValueError(f"Unknown model configuration {run.configuration!r}")
        grouped.setdefault(run.configuration, []).append(run)
    if set(grouped) != set(MODEL_CONFIGURATIONS):
        raise ValueError("Both M1 and M2 must be evaluated")
    expected_folds = {run.fold for run in grouped["M1"]}
    if expected_folds != {run.fold for run in grouped["M2"]} or len(expected_folds) != 4:
        raise ValueError("M1 and M2 must cover the same four inner folds")
    means = {
        name: float(np.mean([run.macro_category_mae for run in config_runs]))
        for name, config_runs in grouped.items()
    }
    selected = min(("M1", "M2"), key=lambda name: (means[name], 0 if name == "M1" else 1))
    selected_epochs = [run.best_epoch for run in grouped[selected]]
    epoch = int(statistics.median(selected_epochs))
    return SelectedConfiguration(selected, epoch, means[selected])


def select_final_training_choice(
    outer_selections: list[SelectedConfiguration],
) -> SelectedConfiguration:
    """Choose modal configuration and median epoch across five outer folds."""

    if len(outer_selections) != 5:
        raise ValueError("Final selection requires all five outer-fold selections")
    counts = {
        name: sum(selection.configuration == name for selection in outer_selections)
        for name in MODEL_CONFIGURATIONS
    }
    selected = min(("M1", "M2"), key=lambda name: (-counts[name], 0 if name == "M1" else 1))
    return SelectedConfiguration(
        configuration=selected,
        epoch=int(statistics.median(selection.epoch for selection in outer_selections)),
        mean_macro_category_mae=float(
            np.mean([selection.mean_macro_category_mae for selection in outer_selections])
        ),
    )


try:  # pragma: no cover - environment-dependent
    import torch
    from torch.utils.data import Dataset
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    Dataset = object  # type: ignore[misc,assignment]


if torch_available():

    class PairedImageDataset(Dataset[dict[str, Any]]):
        """Manifest-backed Torch dataset that never exposes mass/category as inputs."""

        def __init__(
            self,
            records: list[ManifestRecord],
            dataset_root: str | Path,
            *,
            training: bool,
            seed: int = SEED,
        ) -> None:
            self.records = [record for record in records if record.is_valid]
            self.root = Path(dataset_root)
            self.training = training
            self.transform = PairedTrainTransform(seed=seed) if training else None

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int) -> dict[str, Any]:
            record = self.records[index]
            before_path, after_path = self.root / record.before_path, self.root / record.after_path
            if self.transform is None:
                before = deterministic_preprocess(before_path)
                after = deterministic_preprocess(after_path)
            else:
                before, after = self.transform(before_path, after_path)
            return {
                "before": torch.from_numpy(before),
                "after": torch.from_numpy(after),
                "target": torch.tensor(record.leftover_fraction, dtype=torch.float32),
                "category": record.category,
                "sample_id": record.sample_id,
            }


else:

    class PairedImageDataset:  # type: ignore[no-redef]
        def __init__(self, *_: Any, **__: Any) -> None:
            raise missing_extra("Torch dataset", "train", "torch")


def seed_everything(seed: int = SEED) -> None:
    """Seed every runtime and fail closed if a deterministic kernel is unavailable."""

    random.seed(seed)
    np.random.seed(seed)
    if torch is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        torch.use_deterministic_algorithms(True, warn_only=False)
        if hasattr(torch.backends, "cudnn"):
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True


@dataclass(frozen=True, slots=True)
class FitResult:
    best_epoch: int
    best_macro_category_mae: float
    epochs_completed: int
    state_dict: dict[str, Any]


def fit_model(
    model: Any,
    train_loader: Any,
    validation_loader: Any,
    configuration: ModelConfiguration,
    *,
    device: str = "cpu",
    maximum_epochs: int = 80,
    patience: int = 12,
    freeze_epochs: int = 5,
    weight_decay: float = 1e-4,
    gradient_clip: float = 1.0,
    interval_weight: float = 0.5,
    seed: int = SEED,
) -> FitResult:
    """Fit one inner/final run with the locked freeze and early-stop policy."""

    if torch is None:
        raise missing_extra("Model training", "train", "torch")
    if maximum_epochs < 1 or patience < 1 or freeze_epochs < 0:
        raise ValueError("Epoch and patience settings are invalid")
    seed_everything(seed)
    target_device = torch.device(device)
    model.to(target_device)
    configure_trainable_stages(model, encoder_frozen=True)
    criterion = QuantileRegressionLoss(interval_weight=interval_weight)

    def make_optimizer() -> Any:
        encoder_parameters = [
            parameter for parameter in model.encoder.parameters() if parameter.requires_grad
        ]
        groups = [{"params": model.head.parameters(), "lr": configuration.head_learning_rate}]
        if encoder_parameters:
            groups.append(
                {"params": encoder_parameters, "lr": configuration.encoder_learning_rate}
            )
        return torch.optim.AdamW(groups, weight_decay=weight_decay)

    optimizer = make_optimizer()
    use_amp = target_device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    best_score = float("inf")
    best_epoch = 0
    best_state: dict[str, Any] | None = None
    stale = 0
    encoder_frozen = True
    for epoch in range(1, maximum_epochs + 1):
        if epoch == freeze_epochs + 1:
            encoder_frozen = False
            configure_trainable_stages(model, encoder_frozen=False)
            optimizer = make_optimizer()
        model.train()
        # Frozen stages must not update BatchNorm running statistics. After
        # unfreezing, only the final two feature stages enter training mode.
        model.encoder.eval()
        if not encoder_frozen:
            stages = getattr(model.encoder, "blocks", None) or getattr(
                model.encoder, "features", None
            )
            if stages is None:
                resnet_stages = [
                    getattr(model.encoder, name, None)
                    for name in ("layer1", "layer2", "layer3", "layer4")
                ]
                if all(stage is not None for stage in resnet_stages):
                    stages = resnet_stages
            if stages is None:
                raise ValueError(
                    "Encoder does not expose MobileNet/ViT blocks, features, or ResNet layers"
                )
            stage_list = list(stages) if isinstance(stages, list) else list(stages.children())
            for stage in stage_list[-2:]:
                stage.train()
        for batch in train_loader:
            before = batch["before"].to(target_device)
            after = batch["after"].to(target_device)
            targets = batch["target"].to(target_device)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(target_device.type, enabled=use_amp):
                predictions = model(before, after)
                loss = criterion(predictions, targets)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), gradient_clip)
            scaler.step(optimizer)
            scaler.update()

        score = _evaluate_validation_macro_mae(model, validation_loader, target_device)
        if score < best_score - 1e-12:
            best_score, best_epoch, stale = score, epoch, 0
            best_state = {
                key: value.detach().cpu().clone() for key, value in model.state_dict().items()
            }
        else:
            stale += 1
            if stale >= patience:
                break
    if best_state is None:
        raise RuntimeError("Training produced no checkpoint")
    return FitResult(best_epoch, best_score, epoch, best_state)


def _evaluate_validation_macro_mae(model: Any, loader: Any, device: Any) -> float:
    if torch is None:
        raise missing_extra("Validation", "train", "torch")
    model.eval()
    targets: list[float] = []
    predictions: list[float] = []
    categories: list[str] = []
    with torch.inference_mode():
        for batch in loader:
            output = model(batch["before"].to(device), batch["after"].to(device))
            targets.extend(batch["target"].cpu().numpy().tolist())
            predictions.extend(output[:, 1].cpu().numpy().tolist())
            categories.extend(list(batch["category"]))
    return macro_category_mae(np.asarray(targets), np.asarray(predictions), np.asarray(categories))
