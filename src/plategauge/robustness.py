"""Frozen image perturbations for post-model robustness evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageEnhance, ImageFilter

from .transforms import ImageLike, load_rgb


@dataclass(frozen=True, slots=True)
class Perturbation:
    name: str
    mode: Literal["shared", "after_only"]
    parameter: float


FROZEN_PERTURBATIONS: tuple[Perturbation, ...] = (
    Perturbation("shared_rotation_plus_5", "shared", 5.0),
    Perturbation("shared_rotation_minus_5", "shared", -5.0),
    Perturbation("shared_translation_plus_5pct", "shared", 0.05),
    Perturbation("shared_center_crop_5pct", "shared", 0.05),
    Perturbation("jpeg_quality_50", "shared", 50.0),
    Perturbation("brightness_plus_20pct", "shared", 1.20),
    Perturbation("brightness_minus_20pct", "shared", 0.80),
    Perturbation("contrast_plus_20pct", "shared", 1.20),
    Perturbation("contrast_minus_20pct", "shared", 0.80),
    Perturbation("gaussian_blur_sigma_1", "shared", 1.0),
    Perturbation("after_brightness_plus_20pct", "after_only", 1.20),
    Perturbation("after_gaussian_blur_sigma_1", "after_only", 1.0),
    Perturbation("after_translation_plus_5pct", "after_only", 0.05),
)


def _translate(image: Image.Image, fraction: float) -> Image.Image:
    dx, dy = image.width * fraction, image.height * fraction
    return image.transform(
        image.size,
        Image.Transform.AFFINE,
        (1.0, 0.0, -dx, 0.0, 1.0, -dy),
        resample=Image.Resampling.BILINEAR,
        fillcolor=(0, 0, 0),
    )


def _center_crop_and_resize(image: Image.Image, fraction: float) -> Image.Image:
    dx, dy = round(image.width * fraction), round(image.height * fraction)
    cropped = image.crop((dx, dy, image.width - dx, image.height - dy))
    return cropped.resize(image.size, Image.Resampling.BICUBIC)


def _jpeg(image: Image.Image, quality: int) -> Image.Image:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    with Image.open(buffer) as decoded:
        result: Image.Image = decoded.convert("RGB").copy()
        return result


def _apply(image: Image.Image, name: str, parameter: float) -> Image.Image:
    if "rotation" in name:
        return image.rotate(parameter, resample=Image.Resampling.BILINEAR, fillcolor=(0, 0, 0))
    if "translation" in name:
        return _translate(image, parameter)
    if "center_crop" in name:
        return _center_crop_and_resize(image, parameter)
    if name == "jpeg_quality_50":
        return _jpeg(image, int(parameter))
    if "brightness" in name:
        return ImageEnhance.Brightness(image).enhance(parameter)
    if "contrast" in name:
        return ImageEnhance.Contrast(image).enhance(parameter)
    if "gaussian_blur" in name:
        return image.filter(ImageFilter.GaussianBlur(radius=parameter))
    raise ValueError(f"Unknown frozen perturbation {name!r}")


def perturb_pair(
    before: ImageLike, after: ImageLike, perturbation: Perturbation
) -> tuple[Image.Image, Image.Image]:
    """Apply one named frozen scenario without changing the original images."""

    before_image, after_image = load_rgb(before), load_rgb(after)
    if perturbation.mode == "shared":
        return (
            _apply(before_image, perturbation.name, perturbation.parameter),
            _apply(after_image, perturbation.name, perturbation.parameter),
        )
    return before_image, _apply(after_image, perturbation.name, perturbation.parameter)


def swapped_pair(before: ImageLike, after: ImageLike) -> tuple[Image.Image, Image.Image]:
    """Frozen misuse test: reverse temporal order."""

    return load_rgb(after), load_rgb(before)


def same_image_pair(image: ImageLike) -> tuple[Image.Image, Image.Image]:
    """Frozen misuse test: supply the same image twice."""

    loaded = load_rgb(image)
    return loaded.copy(), loaded.copy()
