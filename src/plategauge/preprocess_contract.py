"""Generate and verify exact Python-to-browser preprocessing golden fixtures."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .errors import DataIntegrityError
from .release_artifacts import canonical_json_sha256, read_json_object, write_immutable_json
from .transforms import deterministic_preprocess, load_rgb

PREPROCESS_GOLDEN_SCHEMA_VERSION = "1.0"
RESIZE_SHORT_EDGE = 256
CROP_SIZE = 224


@dataclass(frozen=True, slots=True)
class FixtureDefinition:
    fixture_id: str
    width: int
    height: int
    kind: str
    color: tuple[int, int, int] | None = None


FIXTURE_DEFINITIONS: tuple[FixtureDefinition, ...] = (
    FixtureDefinition("identity_pattern", 256, 256, "pattern"),
    FixtureDefinition("landscape_uniform", 640, 480, "uniform", (17, 101, 233)),
    FixtureDefinition("portrait_uniform", 480, 640, "uniform", (201, 77, 31)),
)


def preprocess_geometry(width: int, height: int) -> dict[str, int]:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    scale = RESIZE_SHORT_EDGE / min(width, height)
    resized_width = max(RESIZE_SHORT_EDGE, round(width * scale))
    resized_height = max(RESIZE_SHORT_EDGE, round(height * scale))
    return {
        "source_width": width,
        "source_height": height,
        "resized_width": resized_width,
        "resized_height": resized_height,
        "crop_left": (resized_width - CROP_SIZE) // 2,
        "crop_top": (resized_height - CROP_SIZE) // 2,
        "crop_width": CROP_SIZE,
        "crop_height": CROP_SIZE,
    }


def _source_image(definition: FixtureDefinition) -> Image.Image:
    if definition.kind == "uniform" and definition.color is not None:
        return Image.new("RGB", (definition.width, definition.height), definition.color)
    if definition.kind != "pattern":
        raise DataIntegrityError(f"Unknown preprocessing fixture kind: {definition.kind}")
    y, x = np.indices((definition.height, definition.width), dtype=np.uint16)
    array = np.empty((definition.height, definition.width, 3), dtype=np.uint8)
    array[..., 0] = ((3 * x + 5 * y + 11) % 256).astype(np.uint8)
    array[..., 1] = ((7 * x + 2 * y + 37) % 256).astype(np.uint8)
    array[..., 2] = ((x + 11 * y + 83) % 256).astype(np.uint8)
    return Image.fromarray(array)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return buffer.getvalue()


def _preprocessed_rgb(image: Image.Image) -> Image.Image:
    geometry = preprocess_geometry(*image.size)
    resized = load_rgb(image).resize(
        (geometry["resized_width"], geometry["resized_height"]),
        Image.Resampling.BICUBIC,
    )
    return resized.crop(
        (
            geometry["crop_left"],
            geometry["crop_top"],
            geometry["crop_left"] + CROP_SIZE,
            geometry["crop_top"] + CROP_SIZE,
        )
    )


def _fixture_entry(definition: FixtureDefinition, source_bytes: bytes) -> dict[str, Any]:
    with Image.open(BytesIO(source_bytes)) as decoded:
        source = decoded.convert("RGB").copy()
    processed = _preprocessed_rgb(source)
    rgba = np.asarray(processed.convert("RGBA"), dtype=np.uint8).tobytes(order="C")
    tensor = np.ascontiguousarray(deterministic_preprocess(source), dtype="<f4")
    if len(rgba) != CROP_SIZE * CROP_SIZE * 4 or tensor.shape != (3, CROP_SIZE, CROP_SIZE):
        raise DataIntegrityError("Golden preprocessing produced an unexpected shape")
    return {
        "fixture_id": definition.fixture_id,
        "source_file": f"{definition.fixture_id}.png",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "geometry": preprocess_geometry(definition.width, definition.height),
        "expected_rgba_sha256": hashlib.sha256(rgba).hexdigest(),
        "expected_rgba_bytes": len(rgba),
        "expected_normalized_chw_float32_sha256": hashlib.sha256(
            tensor.tobytes(order="C")
        ).hexdigest(),
        "expected_tensor_shape": [3, CROP_SIZE, CROP_SIZE],
        "expected_tensor_float_count": int(tensor.size),
    }


def expected_golden_payload() -> tuple[dict[str, Any], dict[str, bytes]]:
    sources: dict[str, bytes] = {}
    entries: list[dict[str, Any]] = []
    for definition in FIXTURE_DEFINITIONS:
        source = _png_bytes(_source_image(definition))
        filename = f"{definition.fixture_id}.png"
        sources[filename] = source
        entries.append(_fixture_entry(definition, source))
    core: dict[str, Any] = {
        "schema_version": PREPROCESS_GOLDEN_SCHEMA_VERSION,
        "kind": "python_browser_preprocessing_golden",
        "pipeline": {
            "orientation": "EXIF transpose",
            "color": "RGB",
            "resize_short_edge": RESIZE_SHORT_EDGE,
            "resize_rounding": "ties-to-even",
            "interpolation": "bicubic",
            "center_crop": CROP_SIZE,
            "browser_output": "RGBA uint8",
            "model_tensor": "CHW float32 ImageNet-normalized little-endian",
        },
        "scope_note": (
            "The patterned identity-resize fixture verifies every crop/channel/normalization byte. "
            "Uniform landscape and portrait fixtures verify resize geometry without relying on "
            "browser-specific interpolation rounding."
        ),
        "fixtures": entries,
    }
    return core | {"evidence_sha256": canonical_json_sha256(core)}, sources


def generate_preprocess_golden(directory: str | Path) -> dict[str, Any]:
    """Create fixtures once; an existing differing byte is a hard failure."""

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    payload, sources = expected_golden_payload()
    for filename, value in sources.items():
        destination = root / filename
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != value:
                raise DataIntegrityError(f"Existing golden fixture differs: {destination}")
            continue
        try:
            with destination.open("xb") as handle:
                handle.write(value)
        except FileExistsError as exc:  # pragma: no cover - concurrent generation
            raise DataIntegrityError(
                f"Golden fixture appeared concurrently: {destination}"
            ) from exc
    manifest = root / "manifest.json"
    if manifest.exists():
        if read_json_object(manifest) != payload:
            raise DataIntegrityError("Existing preprocessing golden manifest differs")
    else:
        write_immutable_json(manifest, payload)
    verify_preprocess_golden(root)
    return payload


def verify_preprocess_golden(directory: str | Path) -> dict[str, Any]:
    """Recompute every Python expectation and validate immutable source bytes."""

    root = Path(directory)
    payload = read_json_object(root / "manifest.json")
    digest = payload.get("evidence_sha256")
    core = {key: value for key, value in payload.items() if key != "evidence_sha256"}
    if digest != canonical_json_sha256(core):
        raise DataIntegrityError("Preprocessing golden manifest evidence hash mismatch")
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != len(FIXTURE_DEFINITIONS):
        raise DataIntegrityError("Preprocessing golden fixture count changed")
    definitions = {item.fixture_id: item for item in FIXTURE_DEFINITIONS}
    observed: set[str] = set()
    for entry in fixtures:
        if not isinstance(entry, dict):
            raise DataIntegrityError("Preprocessing fixture entry must be an object")
        fixture_id = str(entry.get("fixture_id"))
        if fixture_id not in definitions or fixture_id in observed:
            raise DataIntegrityError(f"Unknown or repeated preprocessing fixture: {fixture_id}")
        observed.add(fixture_id)
        source_path = root / str(entry.get("source_file"))
        if not source_path.is_file():
            raise DataIntegrityError(f"Missing preprocessing source fixture: {source_path}")
        source = source_path.read_bytes()
        if hashlib.sha256(source).hexdigest() != entry.get("source_sha256"):
            raise DataIntegrityError(f"Preprocessing source hash mismatch: {source_path}")
        expected = _fixture_entry(definitions[fixture_id], source)
        if entry != expected:
            raise DataIntegrityError(f"Preprocessing expectation changed: {fixture_id}")
    return payload
