"""Paired image augmentation and frozen inference preprocessing."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

type ImageLike = str | Path | Image.Image
IMAGENET_MEAN = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)[:, None, None]
IMAGENET_STD = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)[:, None, None]


def load_rgb(value: ImageLike) -> Image.Image:
    """Load an image, apply EXIF orientation, remove alpha, and detach from file."""

    if isinstance(value, (str, Path)):
        with Image.open(value) as source:
            return ImageOps.exif_transpose(source).convert("RGB").copy()
    return ImageOps.exif_transpose(value).convert("RGB").copy()


def _resize_shorter_edge(image: Image.Image, size: int) -> Image.Image:
    width, height = image.size
    scale = size / min(width, height)
    resized = (max(size, round(width * scale)), max(size, round(height * scale)))
    return image.resize(resized, Image.Resampling.BICUBIC)


def _center_crop(image: Image.Image, size: int) -> Image.Image:
    width, height = image.size
    left, top = (width - size) // 2, (height - size) // 2
    return image.crop((left, top, left + size, top + size))


def image_to_normalized_chw(image: Image.Image) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32) / 255.0
    chw = np.transpose(array, (2, 0, 1))
    normalized = (chw - IMAGENET_MEAN) / IMAGENET_STD
    if normalized.shape != (3, 224, 224) or not np.isfinite(normalized).all():
        raise ValueError("Preprocessing produced an invalid tensor")
    return normalized.astype(np.float32, copy=False)


def deterministic_preprocess(value: ImageLike) -> np.ndarray:
    """Model-card preprocessing: EXIF transpose, RGB, 256 resize, 224 center crop."""

    image = _center_crop(_resize_shorter_edge(load_rgb(value), 256), 224)
    return image_to_normalized_chw(image)


@dataclass(frozen=True, slots=True)
class PairedAugmentationConfig:
    horizontal_flip_probability: float = 0.5
    maximum_rotation_degrees: float = 8.0
    maximum_translation_fraction: float = 0.05
    minimum_scale: float = 0.95
    maximum_scale: float = 1.05
    brightness_jitter: float = 0.10
    contrast_jitter: float = 0.10


def _affine(
    image: Image.Image,
    *,
    angle: float,
    translate_x: float,
    translate_y: float,
    scale: float,
) -> Image.Image:
    width, height = image.size
    center_x, center_y = width / 2.0, height / 2.0
    inverse_scale = 1.0 / scale
    coefficients = (
        inverse_scale,
        0.0,
        center_x - center_x * inverse_scale - translate_x,
        0.0,
        inverse_scale,
        center_y - center_y * inverse_scale - translate_y,
    )
    scaled = image.transform(
        image.size,
        Image.Transform.AFFINE,
        coefficients,
        resample=Image.Resampling.BILINEAR,
        fillcolor=(0, 0, 0),
    )
    return scaled.rotate(
        angle,
        resample=Image.Resampling.BILINEAR,
        expand=False,
        fillcolor=(0, 0, 0),
    )


class PairedTrainTransform:
    """Apply identical geometry and independent mild color jitter to a pair."""

    def __init__(
        self,
        config: PairedAugmentationConfig | None = None,
        *,
        seed: int | None = None,
    ) -> None:
        self.config = config or PairedAugmentationConfig()
        self.random = random.Random(seed)
        if not 0.0 <= self.config.horizontal_flip_probability <= 1.0:
            raise ValueError("Flip probability must lie in [0, 1]")
        if not 0 < self.config.minimum_scale <= self.config.maximum_scale:
            raise ValueError("Scale range is invalid")

    def _color(self, image: Image.Image) -> Image.Image:
        brightness = self.random.uniform(
            1.0 - self.config.brightness_jitter, 1.0 + self.config.brightness_jitter
        )
        contrast = self.random.uniform(
            1.0 - self.config.contrast_jitter, 1.0 + self.config.contrast_jitter
        )
        return ImageEnhance.Contrast(ImageEnhance.Brightness(image).enhance(brightness)).enhance(
            contrast
        )

    def __call__(self, before: ImageLike, after: ImageLike) -> tuple[np.ndarray, np.ndarray]:
        before_image = _center_crop(_resize_shorter_edge(load_rgb(before), 256), 224)
        after_image = _center_crop(_resize_shorter_edge(load_rgb(after), 256), 224)
        flip = self.random.random() < self.config.horizontal_flip_probability
        angle = self.random.uniform(
            -self.config.maximum_rotation_degrees, self.config.maximum_rotation_degrees
        )
        maximum_translation = 224.0 * self.config.maximum_translation_fraction
        translate_x = self.random.uniform(-maximum_translation, maximum_translation)
        translate_y = self.random.uniform(-maximum_translation, maximum_translation)
        scale = self.random.uniform(self.config.minimum_scale, self.config.maximum_scale)
        if flip:
            before_image = ImageOps.mirror(before_image)
            after_image = ImageOps.mirror(after_image)
        before_image = _affine(
            before_image,
            angle=angle,
            translate_x=translate_x,
            translate_y=translate_y,
            scale=scale,
        )
        after_image = _affine(
            after_image,
            angle=angle,
            translate_x=translate_x,
            translate_y=translate_y,
            scale=scale,
        )
        return (
            image_to_normalized_chw(self._color(before_image)),
            image_to_normalized_chw(self._color(after_image)),
        )
