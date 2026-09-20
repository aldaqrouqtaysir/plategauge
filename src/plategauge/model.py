"""Optional Torch paired-encoder quantile models.

This module remains importable without Torch or timm so data-audit and statistics
work in minimal environments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .data import sha256_file
from .errors import DataIntegrityError, missing_extra

MOBILENET_CHECKPOINT = "mobilenetv3_small_100.lamb_in1k"
MOBILENET_HF_REPOSITORY = "timm/mobilenetv3_small_100.lamb_in1k"
MOBILENET_HF_REVISION = "1824797e7887cbec1990e4adbd6675960a36c589"
MOBILENET_WEIGHTS_FILENAME = "model.safetensors"
MOBILENET_WEIGHTS_SIZE = 10_241_912
MOBILENET_WEIGHTS_SHA256 = "46d2c063b18125884c48937afa4c49e18128869e52e8db96df48bf0a4d7ff697"
RESNET_CHECKPOINT = "resnet50.a1_in1k"
DINOV2_CHECKPOINT = "vit_small_patch14_dinov2.lvd142m"
QUANTILES = (0.05, 0.50, 0.95)

try:  # pragma: no cover - both branches are exercised in different environments
    import torch
    from torch import Tensor, nn
    from torch.nn import functional as F
except ImportError:  # pragma: no cover - tested through stub behavior
    torch = None  # type: ignore[assignment]
    Tensor = Any  # type: ignore[misc,assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]


def torch_available() -> bool:
    return torch is not None


def _require_timm() -> Any:
    try:
        import timm
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise missing_extra("Model construction", "train", "timm") from exc
    return timm


if nn is not None:

    def ordered_quantiles_torch(raw: Tensor) -> Tensor:
        """Differentiable mapping to bounded, ordered low/median/high quantiles."""

        if raw.shape[-1] != 3:
            raise ValueError("Quantile head must emit exactly three logits")
        probabilities = torch.sigmoid(raw)
        median = probabilities[..., 1]
        lower = median * probabilities[..., 0]
        upper = median + (1.0 - median) * probabilities[..., 2]
        return torch.stack((lower, median, upper), dim=-1)


    class PairedQuantileRegressor(nn.Module):
        """Shared encoder with late pair fusion and an ordered quantile head."""

        def __init__(self, encoder: nn.Module, feature_dim: int, *, dropout: float) -> None:
            super().__init__()
            self.encoder = encoder
            self.feature_dim = feature_dim
            self.head = nn.Sequential(
                nn.LayerNorm(feature_dim * 4),
                nn.Linear(feature_dim * 4, 256),
                nn.Hardswish(),
                nn.Dropout(dropout),
                nn.Linear(256, 3),
            )

        def _encode(self, image: Tensor) -> Tensor:
            features = self.encoder(image)
            if isinstance(features, (tuple, list)):
                features = features[-1]
            if features.ndim > 2:
                features = features.mean(dim=tuple(range(2, features.ndim)))
            if features.shape[-1] != self.feature_dim:
                raise RuntimeError(
                    f"Encoder returned {features.shape[-1]} features, expected {self.feature_dim}"
                )
            return cast(Tensor, features)

        def forward(self, before: Tensor, after: Tensor) -> Tensor:
            before_features = self._encode(before)
            after_features = self._encode(after)
            fused = torch.cat(
                (
                    before_features,
                    after_features,
                    torch.abs(before_features - after_features),
                    before_features * after_features,
                ),
                dim=-1,
            )
            return ordered_quantiles_torch(self.head(fused))


    class AfterOnlyQuantileRegressor(nn.Module):
        """Preregistered after-image-only ablation using the same head capacity."""

        def __init__(self, encoder: nn.Module, feature_dim: int, *, dropout: float) -> None:
            super().__init__()
            self.encoder = encoder
            self.feature_dim = feature_dim
            self.head = nn.Sequential(
                nn.LayerNorm(feature_dim),
                nn.Linear(feature_dim, 256),
                nn.Hardswish(),
                nn.Dropout(dropout),
                nn.Linear(256, 3),
            )

        def forward(self, after: Tensor) -> Tensor:
            features = self.encoder(after)
            if features.ndim > 2:
                features = features.mean(dim=tuple(range(2, features.ndim)))
            return ordered_quantiles_torch(self.head(features))


    class QuantileRegressionLoss(nn.Module):
        """Smooth-L1 median loss plus weighted 0.05/0.95 pinball losses."""

        def __init__(self, *, interval_weight: float = 0.5) -> None:
            super().__init__()
            if interval_weight < 0:
                raise ValueError("interval_weight must be non-negative")
            self.interval_weight = interval_weight

        @staticmethod
        def _pinball(target: Tensor, prediction: Tensor, quantile: float) -> Tensor:
            residual = target - prediction
            return torch.maximum(quantile * residual, (quantile - 1.0) * residual).mean()

        def forward(self, predictions: Tensor, targets: Tensor) -> Tensor:
            target = targets.reshape(-1)
            if predictions.ndim != 2 or predictions.shape[1] != 3:
                raise ValueError("Predictions must have shape [batch, 3]")
            median_loss = F.smooth_l1_loss(predictions[:, 1], target)
            interval_loss = self._pinball(target, predictions[:, 0], 0.05) + self._pinball(
                target, predictions[:, 2], 0.95
            )
            return median_loss + self.interval_weight * interval_loss


else:

    def ordered_quantiles_torch(raw: Any) -> Any:
        raise missing_extra("Torch quantile ordering", "train", "torch")


    class PairedQuantileRegressor:  # type: ignore[no-redef]
        def __init__(self, *_: Any, **__: Any) -> None:
            raise missing_extra("Paired model", "train", "torch")


    class AfterOnlyQuantileRegressor:  # type: ignore[no-redef]
        def __init__(self, *_: Any, **__: Any) -> None:
            raise missing_extra("After-only model", "train", "torch")


    class QuantileRegressionLoss:  # type: ignore[no-redef]
        def __init__(self, *_: Any, **__: Any) -> None:
            raise missing_extra("Quantile loss", "train", "torch")


def verify_mobilenet_weights(path: str | Path) -> Path:
    """Verify the exact pinned Hugging Face artifact before any model loads it."""

    weights_path = Path(path)
    if not weights_path.is_file():
        raise DataIntegrityError(f"Pinned MobileNet weights not found: {weights_path}")
    size = weights_path.stat().st_size
    if size != MOBILENET_WEIGHTS_SIZE:
        raise DataIntegrityError(
            f"Pinned MobileNet size mismatch: expected {MOBILENET_WEIGHTS_SIZE}, found {size}"
        )
    digest = sha256_file(weights_path)
    if digest != MOBILENET_WEIGHTS_SHA256:
        raise DataIntegrityError(
            f"Pinned MobileNet SHA-256 mismatch: expected {MOBILENET_WEIGHTS_SHA256}, found {digest}"
        )
    return weights_path


def build_timm_encoder(
    checkpoint: str,
    *,
    pretrained: bool = True,
    weights_path: str | Path | None = None,
) -> tuple[Any, int]:
    """Build a pooled feature encoder and report its output dimension."""

    if torch is None:
        raise missing_extra("Model construction", "train", "torch")
    timm = _require_timm()
    # Pinned timm safetensors include the original classifier. Load that
    # architecture strictly first, then remove its classifier; asking timm to
    # construct ``num_classes=0`` before checkpoint loading leaves classifier
    # keys unexpected and silently breaks the verified-artifact path.
    arguments: dict[str, Any] = {"pretrained": False}
    if pretrained:
        if checkpoint != MOBILENET_CHECKPOINT:
            raise DataIntegrityError(
                f"No pinned artifact is registered for pretrained checkpoint {checkpoint!r}"
            )
        if weights_path is None:
            raise DataIntegrityError(
                "Pretrained MobileNet requires an explicit local weights_path; implicit downloads are disabled"
            )
        arguments["checkpoint_path"] = str(verify_mobilenet_weights(weights_path))
    encoder = timm.create_model(checkpoint, **arguments)
    reset_classifier = getattr(encoder, "reset_classifier", None)
    if not callable(reset_classifier):
        raise DataIntegrityError(f"Encoder {checkpoint!r} cannot remove its classifier safely")
    reset_classifier(0, global_pool="avg")
    # timm's MobileNetV3 ``num_features`` describes the last convolutional
    # stage (576), while ``forward()`` returns the post-head embedding (1024)
    # when ``num_classes=0``. PlateGauge fuses the latter by contract.
    feature_dim = int(getattr(encoder, "head_hidden_size", encoder.num_features))
    if checkpoint == MOBILENET_CHECKPOINT and feature_dim != 1024:
        raise DataIntegrityError(
            f"Pinned MobileNet embedding changed: expected 1024, found {feature_dim}"
        )
    return encoder, feature_dim


def build_paired_model(
    *,
    checkpoint: str = MOBILENET_CHECKPOINT,
    dropout: float = 0.2,
    pretrained: bool = True,
    weights_path: str | Path | None = None,
) -> Any:
    encoder, feature_dim = build_timm_encoder(
        checkpoint, pretrained=pretrained, weights_path=weights_path
    )
    return PairedQuantileRegressor(encoder, feature_dim, dropout=dropout)


def build_after_only_model(
    *,
    checkpoint: str = MOBILENET_CHECKPOINT,
    dropout: float = 0.2,
    pretrained: bool = True,
    weights_path: str | Path | None = None,
) -> Any:
    encoder, feature_dim = build_timm_encoder(
        checkpoint, pretrained=pretrained, weights_path=weights_path
    )
    return AfterOnlyQuantileRegressor(encoder, feature_dim, dropout=dropout)


def configure_trainable_stages(model: Any, *, encoder_frozen: bool) -> None:
    """Freeze the encoder or unfreeze only its final two feature stages."""

    if torch is None:
        raise missing_extra("Training-stage configuration", "train", "torch")
    for parameter in model.encoder.parameters():
        parameter.requires_grad = False
    for parameter in model.head.parameters():
        parameter.requires_grad = True
    if encoder_frozen:
        return
    stages = getattr(model.encoder, "blocks", None) or getattr(model.encoder, "features", None)
    if stages is None:
        resnet_stages = [
            getattr(model.encoder, name, None) for name in ("layer1", "layer2", "layer3", "layer4")
        ]
        if all(stage is not None for stage in resnet_stages):
            stages = resnet_stages
    if stages is None:
        raise ValueError("Encoder does not expose MobileNet/ViT blocks, features, or ResNet layers")
    stage_list = list(stages) if isinstance(stages, list) else list(stages.children())
    if len(stage_list) < 2:
        raise ValueError("Encoder has fewer than two feature stages")
    for stage in stage_list[-2:]:
        for parameter in stage.parameters():
            parameter.requires_grad = True
