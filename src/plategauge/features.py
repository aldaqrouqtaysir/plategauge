"""Deterministic handcrafted paired-image features for the non-neural baseline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

type ImageInput = str | Path | Image.Image | np.ndarray
HISTOGRAM_BINS = 16


def _as_rgb_array(value: ImageInput, *, size: int = 128) -> np.ndarray:
    if isinstance(value, (str, Path)):
        with Image.open(value) as image:
            rgb = ImageOps.exif_transpose(image).convert("RGB")
    elif isinstance(value, Image.Image):
        rgb = ImageOps.exif_transpose(value).convert("RGB")
    else:
        array = np.asarray(value)
        if array.ndim != 3 or array.shape[2] not in {3, 4}:
            raise ValueError("Expected an HxWx3 or HxWx4 image array")
        if array.shape[2] == 4:
            array = array[:, :, :3]
        if np.issubdtype(array.dtype, np.floating):
            if not np.isfinite(array).all():
                raise ValueError("Image arrays must be finite")
            if float(array.max(initial=0.0)) <= 1.0:
                array = array * 255.0
        rgb = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
    return np.asarray(rgb.resize((size, size), Image.Resampling.BILINEAR), dtype=np.float64) / 255.0


def _histogram(array: np.ndarray) -> np.ndarray:
    values = []
    for channel in range(3):
        hist, _ = np.histogram(array[:, :, channel], bins=HISTOGRAM_BINS, range=(0.0, 1.0))
        normalized = hist.astype(np.float64) / max(1, hist.sum())
        values.extend(normalized)
    return np.asarray(values, dtype=np.float64)


def _rgb_to_hsv(array: np.ndarray) -> np.ndarray:
    """Vectorized RGB-to-HSV conversion with channels in [0, 1]."""

    maximum = array.max(axis=2)
    minimum = array.min(axis=2)
    delta = maximum - minimum
    hue = np.zeros_like(maximum)
    nonzero = delta > 1e-12
    red_max = (array[:, :, 0] == maximum) & nonzero
    green_max = (array[:, :, 1] == maximum) & nonzero
    blue_max = (array[:, :, 2] == maximum) & nonzero
    red_term = np.divide(
        array[:, :, 1] - array[:, :, 2], delta, out=np.zeros_like(delta), where=nonzero
    )
    green_term = np.divide(
        array[:, :, 2] - array[:, :, 0], delta, out=np.zeros_like(delta), where=nonzero
    )
    blue_term = np.divide(
        array[:, :, 0] - array[:, :, 1], delta, out=np.zeros_like(delta), where=nonzero
    )
    hue[red_max] = red_term[red_max] % 6.0
    hue[green_max] = (green_term + 2.0)[green_max]
    hue[blue_max] = (blue_term + 4.0)[blue_max]
    hue /= 6.0
    saturation = np.divide(delta, maximum, out=np.zeros_like(delta), where=maximum > 1e-12)
    return np.stack((hue, saturation, maximum), axis=2)


def _ssim(left: np.ndarray, right: np.ndarray) -> float:
    gray_left = left @ np.asarray([0.299, 0.587, 0.114])
    gray_right = right @ np.asarray([0.299, 0.587, 0.114])
    mu_left, mu_right = float(gray_left.mean()), float(gray_right.mean())
    var_left, var_right = float(gray_left.var(ddof=1)), float(gray_right.var(ddof=1))
    covariance = float(
        ((gray_left - mu_left) * (gray_right - mu_right)).sum() / (gray_left.size - 1)
    )
    c1, c2 = 0.01**2, 0.03**2
    denominator = (mu_left**2 + mu_right**2 + c1) * (var_left + var_right + c2)
    if denominator == 0:
        return 1.0
    return ((2 * mu_left * mu_right + c1) * (2 * covariance + c2)) / denominator


def _edge_density(array: np.ndarray) -> float:
    gray = array @ np.asarray([0.299, 0.587, 0.114])
    gradient_y, gradient_x = np.gradient(gray)
    magnitude = np.hypot(gradient_x, gradient_y)
    return float(np.mean(magnitude > 0.08))


def _foreground_occupancy(array: np.ndarray) -> float:
    border = np.concatenate((array[0], array[-1], array[:, 0], array[:, -1]), axis=0)
    background = np.median(border, axis=0)
    distance = np.linalg.norm(array - background, axis=2)
    adaptive_threshold = max(0.08, float(np.quantile(distance, 0.25)) * 1.5)
    return float(np.mean(distance > adaptive_threshold))


def handcrafted_feature_names() -> tuple[str, ...]:
    names: list[str] = []
    for color_space in ("rgb", "hsv"):
        for channel in range(3):
            for bin_index in range(HISTOGRAM_BINS):
                names.append(f"abs_{color_space}_hist_c{channel}_b{bin_index:02d}")
    names.extend(
        (
            "ssim",
            "edge_density_before",
            "edge_density_after",
            "edge_density_abs_change",
            "foreground_before",
            "foreground_after",
            "foreground_abs_change",
            "absdiff_mean",
            "absdiff_std",
            "absdiff_median",
            "absdiff_p90",
            "absdiff_max",
            "signed_diff_mean",
            "signed_diff_std",
            "absdiff_red_mean",
            "absdiff_green_mean",
            "absdiff_blue_mean",
        )
    )
    return tuple(names)


def extract_handcrafted_features(before: ImageInput, after: ImageInput) -> np.ndarray:
    """Extract paired RGB/HSV, SSIM, edge, occupancy, and difference features."""

    before_array = _as_rgb_array(before)
    after_array = _as_rgb_array(after)
    features: list[float] = []
    features.extend(np.abs(_histogram(before_array) - _histogram(after_array)))
    before_hsv, after_hsv = _rgb_to_hsv(before_array), _rgb_to_hsv(after_array)
    features.extend(np.abs(_histogram(before_hsv) - _histogram(after_hsv)))
    edge_before, edge_after = _edge_density(before_array), _edge_density(after_array)
    occupancy_before = _foreground_occupancy(before_array)
    occupancy_after = _foreground_occupancy(after_array)
    absolute_difference = np.abs(after_array - before_array)
    signed_difference = after_array - before_array
    features.extend(
        (
            _ssim(before_array, after_array),
            edge_before,
            edge_after,
            abs(edge_after - edge_before),
            occupancy_before,
            occupancy_after,
            abs(occupancy_after - occupancy_before),
            float(absolute_difference.mean()),
            float(absolute_difference.std()),
            float(np.median(absolute_difference)),
            float(np.quantile(absolute_difference, 0.90)),
            float(absolute_difference.max()),
            float(signed_difference.mean()),
            float(signed_difference.std()),
            *(float(value) for value in absolute_difference.mean(axis=(0, 1))),
        )
    )
    result = np.asarray(features, dtype=np.float64)
    if result.shape != (len(handcrafted_feature_names()),) or not np.isfinite(result).all():
        raise ValueError("Feature extraction produced an invalid vector")
    return result


def extract_feature_matrix(pairs: list[tuple[ImageInput, ImageInput]]) -> np.ndarray:
    """Extract one row per image pair."""

    if not pairs:
        return np.empty((0, len(handcrafted_feature_names())), dtype=np.float64)
    return np.stack([extract_handcrafted_features(before, after) for before, after in pairs])
