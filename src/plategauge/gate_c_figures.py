"""Deterministic, dependency-free SVG figures for the frozen Gate C evidence.

The generator reads only the two frozen report payloads (plus the immutable run
descriptor for identity verification).  It never opens images, predictions, or
model artifacts.  Existing figures are accepted only when their bytes are
identical, so reruns are idempotent while divergent overwrites fail closed.
"""

from __future__ import annotations

import html
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from .data import sha256_file
from .errors import DataIntegrityError
from .release_artifacts import canonical_json_sha256

FIGURE_SCHEMA_VERSION = "1.0"
PUBLIC_TARGET_SLICE_GATE = 0.15
ROUTINE_DOWNGRADE_THRESHOLD = 0.03

WORKLOAD_LABELS: dict[str, str] = {
    "after_only_mobilenet": "After-only MobileNet",
    "fixed_within_category_wrong_pair": "Wrong-pair control",
    "frozen_paired_dinov2": "Paired DINOv2 (frozen)",
    "handcrafted_ridge": "Handcrafted + Ridge",
    "observer_score_context_only": "Observer score (context only)",
    "paired_mobilenet": "Paired MobileNet",
    "paired_resnet50": "Paired ResNet-50",
    "training_median": "Training-fold median",
}

TARGET_SLICE_ORDER: tuple[tuple[str, str], ...] = (
    ("zero", "0"),
    ("(0,.25]", "(0, 0.25]"),
    ("(.25,.50]", "(0.25, 0.50]"),
    ("(.50,.75]", "(0.50, 0.75]"),
    ("(.75,1)", "(0.75, 1)"),
    ("one", "1"),
)

ROUTINE_CONDITION_ORDER: tuple[tuple[str, str], ...] = (
    ("shared_rotation_plus_5", "Shared rotation +5°"),
    ("shared_rotation_minus_5", "Shared rotation -5°"),
    ("shared_translation_plus_5pct", "Shared translation +5%"),
    ("shared_center_crop_5pct", "Shared center crop 5%"),
    ("jpeg_quality_50", "JPEG quality 50"),
    ("brightness_plus_20pct", "Shared brightness +20%"),
    ("brightness_minus_20pct", "Shared brightness -20%"),
    ("contrast_plus_20pct", "Shared contrast +20%"),
    ("contrast_minus_20pct", "Shared contrast -20%"),
    ("gaussian_blur_sigma_1", "Shared Gaussian blur sigma=1"),
    ("after_brightness_plus_20pct", "After-only brightness +20%"),
    ("after_gaussian_blur_sigma_1", "After-only Gaussian blur sigma=1"),
    ("after_translation_plus_5pct", "After-only translation +5%"),
)

FIGURE_FILENAMES: dict[str, str] = {
    "workload_macro_mae": "gate_c_workload_macro_mae.svg",
    "category_scatter": "gate_c_paired_vs_after_only_by_category.svg",
    "target_slices": "gate_c_target_slice_micro_mae.svg",
    "robustness_delta": "gate_c_routine_robustness_delta.svg",
}


@dataclass(frozen=True, slots=True)
class NamedValue:
    key: str
    label: str
    value: float


@dataclass(frozen=True, slots=True)
class CategoryPoint:
    category: str
    after_only_mae: float
    paired_mae: float


@dataclass(frozen=True, slots=True)
class GateCFigureData:
    run_id: str
    protocol_id: str
    manifest_sha256: str
    run_descriptor_sha256: str
    results_sha256: str
    robustness_sha256: str
    robustness_evidence_sha256: str
    workloads: tuple[NamedValue, ...]
    categories: tuple[CategoryPoint, ...]
    target_slices: tuple[NamedValue, ...]
    routine_deltas: tuple[NamedValue, ...]

    def source_identity(self) -> dict[str, str]:
        return {
            "manifest_sha256": self.manifest_sha256,
            "protocol_id": self.protocol_id,
            "results_sha256": self.results_sha256,
            "robustness_evidence_sha256": self.robustness_evidence_sha256,
            "robustness_sha256": self.robustness_sha256,
            "run_descriptor_sha256": self.run_descriptor_sha256,
            "run_id": self.run_id,
        }


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"Non-finite JSON constant is forbidden: {value}")


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise DataIntegrityError(f"{label} must be a regular, non-symlink JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DataIntegrityError(f"Cannot read strict {label} JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DataIntegrityError(f"{label} JSON root must be an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DataIntegrityError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DataIntegrityError(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise DataIntegrityError(f"{label} must be a non-empty string")
    return value


def _sha256(value: object, label: str) -> str:
    digest = _string(value, label)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise DataIntegrityError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise DataIntegrityError(f"{label} must be an integer >= {minimum}")
    return value


def _number(
    value: object,
    label: str,
    *,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DataIntegrityError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise DataIntegrityError(f"{label} must be finite and in [{minimum}, {maximum}]")
    return result


def _same(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)


def _validate_run_descriptor(
    run_path: Path,
    *,
    expected_sha256: str,
    run_id: str,
    protocol_id: str,
) -> None:
    actual_sha256 = sha256_file(run_path)
    if actual_sha256 != expected_sha256:
        raise DataIntegrityError(
            "Run descriptor hash differs from the hash bound by the frozen reports"
        )
    run = _read_json_object(run_path, "run descriptor")
    if _string(run.get("run_id"), "run descriptor run_id") != run_id:
        raise DataIntegrityError("Run descriptor run_id differs from the frozen reports")
    protocol = _mapping(run.get("protocol"), "run descriptor protocol")
    if _string(protocol.get("protocol_id"), "run descriptor protocol_id") != protocol_id:
        raise DataIntegrityError("Run descriptor protocol_id differs from the frozen reports")


def _extract_workloads(results: Mapping[str, Any]) -> tuple[NamedValue, ...]:
    workloads = _mapping(results.get("workloads"), "results workloads")
    if set(workloads) != set(WORKLOAD_LABELS):
        raise DataIntegrityError("Results must contain exactly the eight frozen workloads")
    values: list[NamedValue] = []
    for key, label in WORKLOAD_LABELS.items():
        workload = _mapping(workloads[key], f"workload {key}")
        overall = _mapping(workload.get("overall"), f"workload {key} overall")
        if _integer(overall.get("category_count"), f"{key} category_count") != 34:
            raise DataIntegrityError(f"{key} must cover exactly 34 categories")
        if _integer(overall.get("n"), f"{key} n") != 514:
            raise DataIntegrityError(f"{key} must cover exactly 514 pairs")
        values.append(
            NamedValue(
                key=key,
                label=label,
                value=_number(overall.get("macro_category_mae"), f"{key} macro MAE"),
            )
        )
    return tuple(values)


def _extract_categories(results: Mapping[str, Any]) -> tuple[CategoryPoint, ...]:
    workloads = _mapping(results.get("workloads"), "results workloads")
    paired = _mapping(workloads.get("paired_mobilenet"), "paired workload")
    after = _mapping(workloads.get("after_only_mobilenet"), "after-only workload")
    paired_categories = _mapping(paired.get("per_category"), "paired categories")
    after_categories = _mapping(after.get("per_category"), "after-only categories")
    expected = {f"{index:03d}" for index in range(34)}
    if set(paired_categories) != expected or set(after_categories) != expected:
        raise DataIntegrityError(
            "Paired and after-only reports must cover categories 000 through 033"
        )
    points: list[CategoryPoint] = []
    for category in sorted(expected):
        paired_metrics = _mapping(paired_categories[category], f"paired category {category}")
        after_metrics = _mapping(after_categories[category], f"after-only category {category}")
        paired_n = _integer(paired_metrics.get("n"), f"paired category {category} n", minimum=1)
        after_n = _integer(after_metrics.get("n"), f"after-only category {category} n", minimum=1)
        if paired_n != after_n:
            raise DataIntegrityError(
                f"Category {category} has inconsistent paired/after-only support"
            )
        points.append(
            CategoryPoint(
                category=category,
                after_only_mae=_number(
                    after_metrics.get("macro_category_mae"),
                    f"after-only category {category} MAE",
                ),
                paired_mae=_number(
                    paired_metrics.get("macro_category_mae"),
                    f"paired category {category} MAE",
                ),
            )
        )
    return tuple(points)


def _extract_target_slices(results: Mapping[str, Any]) -> tuple[NamedValue, ...]:
    workloads = _mapping(results.get("workloads"), "results workloads")
    paired = _mapping(workloads.get("paired_mobilenet"), "paired workload")
    slices = _mapping(paired.get("slices"), "paired slices")
    target_range = _mapping(slices.get("target_range"), "paired target-range slices")
    expected = {key for key, _ in TARGET_SLICE_ORDER}
    if set(target_range) != expected:
        raise DataIntegrityError("Paired target-range report differs from the six frozen slices")
    values: list[NamedValue] = []
    count = 0
    for key, label in TARGET_SLICE_ORDER:
        metrics = _mapping(target_range[key], f"target slice {key}")
        count += _integer(metrics.get("n"), f"target slice {key} n", minimum=1)
        values.append(
            NamedValue(
                key=key,
                label=label,
                value=_number(metrics.get("micro_mae"), f"target slice {key} micro MAE"),
            )
        )
    if count != 514:
        raise DataIntegrityError("Target-range slices must partition all 514 valid pairs")

    decisions = _mapping(results.get("decisions"), "results decisions")
    numeric_demo = _mapping(decisions.get("numeric_demo"), "numeric-demo decision")
    reported_worst = _number(
        numeric_demo.get("worst_broad_target_slice_micro_mae"),
        "reported worst target-slice micro MAE",
    )
    if not _same(reported_worst, max(value.value for value in values)):
        raise DataIntegrityError("Numeric-demo worst slice does not match target-range metrics")
    return tuple(values)


def _extract_routine_deltas(robustness: Mapping[str, Any]) -> tuple[NamedValue, ...]:
    clean = _number(robustness.get("clean_macro_category_mae"), "robustness clean macro MAE")
    conditions = _sequence(robustness.get("conditions"), "robustness conditions")
    by_name: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(conditions):
        condition = _mapping(item, f"robustness condition {index}")
        name = _string(condition.get("name"), f"robustness condition {index} name")
        if name in by_name:
            raise DataIntegrityError(f"Duplicate robustness condition: {name}")
        by_name[name] = condition

    clean_condition = by_name.get("clean")
    if clean_condition is None or not _same(
        _number(clean_condition.get("macro_category_mae"), "clean condition MAE"), clean
    ):
        raise DataIntegrityError("Robustness clean condition does not match the clean summary")

    expected_names = {name for name, _ in ROUTINE_CONDITION_ORDER}
    routine_names = {
        name for name, item in by_name.items() if item.get("group") == "routine_perturbation"
    }
    if routine_names != expected_names:
        raise DataIntegrityError("Routine robustness conditions differ from the frozen protocol")

    values: list[NamedValue] = []
    downgrade_expected = False
    for name, label in ROUTINE_CONDITION_ORDER:
        condition = by_name[name]
        macro_mae = _number(condition.get("macro_category_mae"), f"{name} macro MAE")
        delta = _number(
            condition.get("delta_macro_category_mae_from_clean"),
            f"{name} delta",
            minimum=-1.0,
            maximum=1.0,
        )
        threshold = _number(condition.get("routine_downgrade_threshold"), f"{name} threshold")
        if not _same(delta, macro_mae - clean):
            raise DataIntegrityError(f"{name} delta does not equal condition MAE minus clean MAE")
        if not _same(threshold, ROUTINE_DOWNGRADE_THRESHOLD):
            raise DataIntegrityError(f"{name} has an unexpected downgrade threshold")
        exceeds = condition.get("exceeds_routine_downgrade_threshold")
        expected_exceeds = delta > ROUTINE_DOWNGRADE_THRESHOLD
        if not isinstance(exceeds, bool) or exceeds != expected_exceeds:
            raise DataIntegrityError(f"{name} downgrade decision is inconsistent")
        downgrade_expected = downgrade_expected or expected_exceeds
        values.append(NamedValue(key=name, label=label, value=delta))
    if robustness.get("robustness_downgrade_required") is not downgrade_expected:
        raise DataIntegrityError("Top-level robustness downgrade decision is inconsistent")
    return tuple(values)


def load_gate_c_figure_data(
    *,
    results_path: str | Path,
    robustness_path: str | Path,
    run_descriptor_path: str | Path,
) -> GateCFigureData:
    """Validate and extract the exact frozen values used by all four figures."""

    results_file = Path(results_path)
    robustness_file = Path(robustness_path)
    run_file = Path(run_descriptor_path)
    results = _read_json_object(results_file, "results report")
    robustness = _read_json_object(robustness_file, "robustness report")

    if results.get("schemaVersion") != 1 or results.get("frozen") is not True:
        raise DataIntegrityError("Results report is not a frozen schema-version-1 report")
    if (
        robustness.get("schema_version") != "1.0"
        or robustness.get("status") != "complete"
        or robustness.get("kind") != "frozen_final_model_robustness"
    ):
        raise DataIntegrityError("Robustness report identity is not the frozen complete report")

    dataset = _mapping(results.get("dataset"), "results dataset")
    if (
        _integer(dataset.get("valid_pairs"), "valid-pair count") != 514
        or _integer(dataset.get("categories"), "category count") != 34
    ):
        raise DataIntegrityError("Results dataset identity must be 514 pairs across 34 categories")

    run_id = _sha256(results.get("run_id"), "results run_id")
    protocol_id = _sha256(results.get("protocol_id"), "results protocol_id")
    manifest_sha256 = _sha256(results.get("manifest_sha256"), "results manifest hash")
    provenance = _mapping(results.get("provenance"), "results provenance")
    run_descriptor_sha256 = _sha256(
        provenance.get("run_descriptor_sha256"), "results run descriptor hash"
    )

    evidence_sha256 = _sha256(robustness.get("evidence_sha256"), "robustness evidence hash")
    robustness_core = dict(robustness)
    robustness_core.pop("evidence_sha256")
    if canonical_json_sha256(robustness_core) != evidence_sha256:
        raise DataIntegrityError("Robustness canonical evidence hash does not validate")

    model_identity = _mapping(robustness.get("model_identity"), "robustness model identity")
    if _sha256(model_identity.get("run_id"), "robustness run_id") != run_id:
        raise DataIntegrityError("Results and robustness run_id values differ")
    if _sha256(model_identity.get("protocol_id"), "robustness protocol_id") != protocol_id:
        raise DataIntegrityError("Results and robustness protocol_id values differ")
    model_hashes = _mapping(model_identity.get("hashes"), "robustness model hashes")
    if _sha256(model_hashes.get("manifest_sha256"), "robustness manifest hash") != manifest_sha256:
        raise DataIntegrityError("Results and robustness manifest hashes differ")
    if (
        _sha256(
            model_hashes.get("run_descriptor_sha256"),
            "robustness run descriptor hash",
        )
        != run_descriptor_sha256
    ):
        raise DataIntegrityError("Results and robustness run descriptor hashes differ")
    robustness_dataset = _mapping(
        robustness.get("dataset_verification"), "robustness dataset verification"
    )
    if (
        _sha256(robustness_dataset.get("manifest_sha256"), "robustness dataset manifest")
        != manifest_sha256
    ):
        raise DataIntegrityError("Robustness dataset verification has a different manifest")

    _validate_run_descriptor(
        run_file,
        expected_sha256=run_descriptor_sha256,
        run_id=run_id,
        protocol_id=protocol_id,
    )

    return GateCFigureData(
        run_id=run_id,
        protocol_id=protocol_id,
        manifest_sha256=manifest_sha256,
        run_descriptor_sha256=run_descriptor_sha256,
        results_sha256=sha256_file(results_file),
        robustness_sha256=sha256_file(robustness_file),
        robustness_evidence_sha256=evidence_sha256,
        workloads=_extract_workloads(results),
        categories=_extract_categories(results),
        target_slices=_extract_target_slices(results),
        routine_deltas=_extract_routine_deltas(robustness),
    )


def _xml(value: object, *, quote: bool = True) -> str:
    return html.escape(str(value), quote=quote)


def _float_text(value: float) -> str:
    return format(value, ".17g")


def _coordinate(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _metadata(data: GateCFigureData, figure_id: str, values: object) -> str:
    payload = {
        "figure_id": figure_id,
        "schema_version": FIGURE_SCHEMA_VERSION,
        "sources": data.source_identity(),
        "values": values,
    }
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f'<metadata id="{figure_id}-metadata">{_xml(encoded, quote=False)}</metadata>'


def _svg_open(
    *,
    figure_id: str,
    width: int,
    height: int,
    title: str,
    description: str,
) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" '
            f'aria-labelledby="{figure_id}-title {figure_id}-description">'
        ),
        f'<title id="{figure_id}-title">{_xml(title)}</title>',
        f'<desc id="{figure_id}-description">{_xml(description)}</desc>',
        "<style>",
        (
            "text{font-family:Inter,Segoe UI,Arial,sans-serif;fill:#172033}"
            ".title{font-size:25px;font-weight:700}.subtitle{font-size:14px;fill:#475569}"
            ".axis{font-size:13px;fill:#334155}.tick{font-size:12px;fill:#475569}"
            ".value{font-size:12px;font-weight:650}.category{font-size:10px;font-weight:650}"
            ".note{font-size:12px;fill:#475569}.grid{stroke:#dbe3ec;stroke-width:1}"
            ".axis-line{stroke:#64748b;stroke-width:1.25}"
        ),
        "</style>",
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]


def _source_footer(data: GateCFigureData, *, x: float, y: float) -> str:
    return (
        f'<text class="note" x="{_coordinate(x)}" y="{_coordinate(y)}">'
        f"Frozen run {_xml(data.run_id[:12])} · protocol {_xml(data.protocol_id[:12])}"
        "</text>"
    )


def render_workload_macro_mae(data: GateCFigureData) -> str:
    figure_id = "workload-macro-mae"
    ordered = tuple(sorted(data.workloads, key=lambda item: (item.value, item.key)))
    exact = "; ".join(f"{item.label}={_float_text(item.value)}" for item in ordered)
    lines = _svg_open(
        figure_id=figure_id,
        width=1200,
        height=750,
        title="Macro-category MAE across all frozen workloads",
        description=(
            "Lower is better. Paired MobileNet is highlighted in orange and after-only MobileNet "
            f"in blue. Exact values: {exact}."
        ),
    )
    lines.append(
        _metadata(
            data,
            figure_id,
            [{"macro_category_mae": item.value, "workload": item.key} for item in ordered],
        )
    )
    lines.extend(
        [
            '<text class="title" x="48" y="48">Macro-category MAE across frozen workloads</text>',
            '<text class="subtitle" x="48" y="73">Category-disjoint outer predictions · lower is better ←</text>',
        ]
    )
    plot_left, plot_right, plot_top, plot_bottom = 320.0, 1125.0, 112.0, 610.0
    axis_max = 0.42
    for tick in range(0, 9):
        value = tick * 0.05
        x = plot_left + value / axis_max * (plot_right - plot_left)
        lines.append(
            f'<line class="grid" x1="{_coordinate(x)}" y1="{plot_top}" '
            f'x2="{_coordinate(x)}" y2="{plot_bottom}"/>'
        )
        lines.append(
            f'<text class="tick" text-anchor="middle" x="{_coordinate(x)}" y="632">'
            f"{value:.2f}</text>"
        )
    lines.append(
        f'<line class="axis-line" x1="{plot_left}" y1="{plot_bottom}" '
        f'x2="{plot_right}" y2="{plot_bottom}"/>'
    )
    row_height = 58.0
    for index, item in enumerate(ordered):
        y = plot_top + index * row_height + 8
        width = item.value / axis_max * (plot_right - plot_left)
        if item.key == "paired_mobilenet":
            color = "#c2410c"
        elif item.key == "after_only_mobilenet":
            color = "#2563eb"
        else:
            color = "#64748b"
        lines.append(
            f'<text class="axis" text-anchor="end" x="305" y="{_coordinate(y + 24)}">'
            f"{_xml(item.label)}</text>"
        )
        lines.append(
            f'<rect x="{plot_left}" y="{_coordinate(y)}" width="{_coordinate(width)}" '
            f'height="34" rx="4" fill="{color}" data-workload="{_xml(item.key)}" '
            f'data-value="{_float_text(item.value)}"><title>{_xml(item.label)}: '
            f"{_float_text(item.value)}</title></rect>"
        )
        value_x = min(plot_left + width + 9, 1154.0)
        anchor = "end" if value_x >= 1154.0 else "start"
        lines.append(
            f'<text class="value" text-anchor="{anchor}" x="{_coordinate(value_x)}" '
            f'y="{_coordinate(y + 23)}">{item.value:.3f}</text>'
        )
    lines.extend(
        [
            '<rect x="48" y="663" width="14" height="14" rx="2" fill="#c2410c"/>',
            '<text class="note" x="69" y="675">Paired MobileNet (primary)</text>',
            '<rect x="286" y="663" width="14" height="14" rx="2" fill="#2563eb"/>',
            '<text class="note" x="307" y="675">After-only ablation</text>',
            '<text class="note" x="514" y="675">Observer score is contextual, not a deployable model.</text>',
            _source_footer(data, x=48, y=714),
        ]
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _label_positions(
    points: Sequence[tuple[CategoryPoint, float, float]],
    *,
    left: float,
    right: float,
    top: float,
    bottom: float,
) -> dict[str, tuple[float, float]]:
    """Choose deterministic nearby labels while minimizing bounding-box overlap."""

    candidates = (
        (8.0, -7.0),
        (8.0, 13.0),
        (-29.0, -7.0),
        (-29.0, 13.0),
        (2.0, -15.0),
        (2.0, 21.0),
        (20.0, 2.0),
        (-40.0, 2.0),
    )
    placed: list[tuple[float, float, float, float]] = []
    positions: dict[str, tuple[float, float]] = {}
    for point, point_x, point_y in sorted(
        points, key=lambda item: (-item[2], item[1], item[0].category)
    ):
        best: tuple[float, float, float] | None = None
        for rank, (delta_x, delta_y) in enumerate(candidates):
            x = min(max(point_x + delta_x, left), right - 23.0)
            baseline = min(max(point_y + delta_y, top + 10.0), bottom)
            box = (x - 2.0, baseline - 10.0, x + 24.0, baseline + 3.0)
            overlap = 0.0
            for other in placed:
                overlap_x = max(0.0, min(box[2], other[2]) - max(box[0], other[0]))
                overlap_y = max(0.0, min(box[3], other[3]) - max(box[1], other[1]))
                overlap += overlap_x * overlap_y
            score = overlap * 1000.0 + rank
            if best is None or score < best[0]:
                best = (score, x, baseline)
                best_box = box
        if best is None:  # pragma: no cover - candidates are a non-empty constant
            raise AssertionError("No scatter-label candidates")
        positions[point.category] = (best[1], best[2])
        placed.append(best_box)
    return positions


def render_category_scatter(data: GateCFigureData) -> str:
    figure_id = "paired-after-category-scatter"
    exact = "; ".join(
        f"{item.category}:after={_float_text(item.after_only_mae)},paired={_float_text(item.paired_mae)}"
        for item in data.categories
    )
    lines = _svg_open(
        figure_id=figure_id,
        width=1100,
        height=880,
        title="Paired versus after-only category-level MAE",
        description=(
            "Each labeled point is one food category. Points below the y equals x line favor the "
            f"paired model; points above favor after-only. Exact values: {exact}."
        ),
    )
    lines.append(
        _metadata(
            data,
            figure_id,
            [
                {
                    "after_only_macro_category_mae": item.after_only_mae,
                    "category": item.category,
                    "paired_macro_category_mae": item.paired_mae,
                }
                for item in data.categories
            ],
        )
    )
    lines.extend(
        [
            '<text class="title" x="54" y="48">Paired vs after-only error by category</text>',
            '<text class="subtitle" x="54" y="73">34 held-out categories · labels are dataset category IDs</text>',
        ]
    )
    left, right, top, bottom = 126.0, 975.0, 104.0, 752.0
    axis_max = 0.32
    for tick in range(0, 9):
        value = tick * 0.04
        x = left + value / axis_max * (right - left)
        y = bottom - value / axis_max * (bottom - top)
        lines.append(
            f'<line class="grid" x1="{_coordinate(x)}" y1="{top}" '
            f'x2="{_coordinate(x)}" y2="{bottom}"/>'
        )
        lines.append(
            f'<line class="grid" x1="{left}" y1="{_coordinate(y)}" '
            f'x2="{right}" y2="{_coordinate(y)}"/>'
        )
        lines.append(
            f'<text class="tick" text-anchor="middle" x="{_coordinate(x)}" y="775">'
            f"{value:.2f}</text>"
        )
        lines.append(
            f'<text class="tick" text-anchor="end" x="113" y="{_coordinate(y + 4)}">'
            f"{value:.2f}</text>"
        )
    lines.extend(
        [
            f'<line class="axis-line" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>',
            f'<line class="axis-line" x1="{left}" y1="{top}" x2="{left}" y2="{bottom}"/>',
            f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{top}" stroke="#7c3aed" '
            'stroke-width="2" stroke-dasharray="7 6"><title>Equal-error line y=x</title></line>',
            '<text class="note" x="836" y="133" transform="rotate(-37 836 133)">equal error (y=x)</text>',
            '<text class="axis" text-anchor="middle" x="550" y="817">After-only MobileNet category MAE</text>',
            '<text class="axis" text-anchor="middle" x="28" y="428" transform="rotate(-90 28 428)">Paired MobileNet category MAE</text>',
        ]
    )
    plotted: list[tuple[CategoryPoint, float, float]] = []
    for item in data.categories:
        x = left + item.after_only_mae / axis_max * (right - left)
        y = bottom - item.paired_mae / axis_max * (bottom - top)
        plotted.append((item, x, y))
    label_positions = _label_positions(
        plotted, left=left + 2.0, right=right - 2.0, top=top + 2.0, bottom=bottom - 2.0
    )
    for item, x, y in plotted:
        label_x, label_y = label_positions[item.category]
        lines.append(
            f'<line x1="{_coordinate(x)}" y1="{_coordinate(y)}" '
            f'x2="{_coordinate(label_x + 10)}" y2="{_coordinate(label_y - 4)}" '
            'stroke="#94a3b8" stroke-width="0.7"/>'
        )
        lines.append(
            f'<circle cx="{_coordinate(x)}" cy="{_coordinate(y)}" r="5" fill="#c2410c" '
            f'stroke="#ffffff" stroke-width="1.5" data-category="{item.category}" '
            f'data-after-only-mae="{_float_text(item.after_only_mae)}" '
            f'data-paired-mae="{_float_text(item.paired_mae)}"><title>Category {item.category}: '
            f"after-only {_float_text(item.after_only_mae)}, paired {_float_text(item.paired_mae)}"
            "</title></circle>"
        )
        lines.append(
            f'<text class="category" x="{_coordinate(label_x)}" y="{_coordinate(label_y)}" '
            'paint-order="stroke" stroke="#ffffff" stroke-width="3" stroke-linejoin="round">'
            f"{item.category}</text>"
        )
    paired_better = sum(item.paired_mae < item.after_only_mae for item in data.categories)
    lines.append(
        f'<text class="note" x="54" y="847">Paired lower in {paired_better}/34 categories · '
        "orange points above the diagonal favor after-only.</text>"
    )
    lines.append(_source_footer(data, x=722, y=847))
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_target_slices(data: GateCFigureData) -> str:
    figure_id = "paired-target-slice-mae"
    exact = "; ".join(f"{item.label}={_float_text(item.value)}" for item in data.target_slices)
    lines = _svg_open(
        figure_id=figure_id,
        width=1100,
        height=720,
        title="Paired MobileNet micro-MAE by leftover-fraction slice",
        description=(
            "Bars show micro mean absolute error for six mutually exclusive target slices. The "
            f"public numeric-demo gate is 0.15. Exact values: {exact}."
        ),
    )
    lines.append(
        _metadata(
            data,
            figure_id,
            [{"micro_mae": item.value, "target_slice": item.key} for item in data.target_slices],
        )
    )
    lines.extend(
        [
            '<text class="title" x="54" y="48">Error across leftover-fraction slices</text>',
            '<text class="subtitle" x="54" y="73">Paired MobileNet · micro-MAE · lower is better</text>',
        ]
    )
    left, right, top, bottom = 102.0, 1036.0, 108.0, 574.0
    axis_max = 0.30
    for tick in range(0, 7):
        value = tick * 0.05
        y = bottom - value / axis_max * (bottom - top)
        lines.append(
            f'<line class="grid" x1="{left}" y1="{_coordinate(y)}" '
            f'x2="{right}" y2="{_coordinate(y)}"/>'
        )
        lines.append(
            f'<text class="tick" text-anchor="end" x="88" y="{_coordinate(y + 4)}">'
            f"{value:.2f}</text>"
        )
    gate_y = bottom - PUBLIC_TARGET_SLICE_GATE / axis_max * (bottom - top)
    lines.append(
        f'<line x1="{left}" y1="{_coordinate(gate_y)}" x2="{right}" '
        f'y2="{_coordinate(gate_y)}" stroke="#b91c1c" stroke-width="2" '
        'stroke-dasharray="8 6"><title>Public numeric-demo slice gate: 0.15</title></line>'
    )
    lines.append(
        f'<text class="value" text-anchor="end" x="{right}" y="{_coordinate(gate_y - 9)}" '
        'fill="#991b1b">public gate 0.15</text>'
    )
    step = (right - left) / len(data.target_slices)
    bar_width = 92.0
    for index, item in enumerate(data.target_slices):
        x = left + index * step + (step - bar_width) / 2
        height = item.value / axis_max * (bottom - top)
        y = bottom - height
        color = "#c2410c" if item.value > PUBLIC_TARGET_SLICE_GATE else "#0f766e"
        lines.append(
            f'<rect x="{_coordinate(x)}" y="{_coordinate(y)}" width="{bar_width}" '
            f'height="{_coordinate(height)}" rx="5" fill="{color}" '
            f'data-target-slice="{_xml(item.key)}" data-value="{_float_text(item.value)}">'
            f"<title>{_xml(item.label)}: micro-MAE {_float_text(item.value)}</title></rect>"
        )
        lines.append(
            f'<text class="value" text-anchor="middle" x="{_coordinate(x + bar_width / 2)}" '
            f'y="{_coordinate(y - 10)}">{item.value:.3f}</text>'
        )
        lines.append(
            f'<text class="axis" text-anchor="middle" x="{_coordinate(x + bar_width / 2)}" '
            f'y="602">{_xml(item.label)}</text>'
        )
    lines.extend(
        [
            f'<line class="axis-line" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>',
            '<text class="axis" text-anchor="middle" x="568" y="646">True leftover fraction</text>',
            '<text class="axis" text-anchor="middle" x="27" y="341" transform="rotate(-90 27 341)">Micro mean absolute error</text>',
            '<rect x="54" y="672" width="14" height="14" rx="2" fill="#0f766e"/>',
            '<text class="note" x="76" y="684">at or below gate</text>',
            '<rect x="213" y="672" width="14" height="14" rx="2" fill="#c2410c"/>',
            '<text class="note" x="235" y="684">above gate</text>',
            _source_footer(data, x=706, y=684),
        ]
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_robustness_delta(data: GateCFigureData) -> str:
    figure_id = "routine-robustness-delta"
    exact = "; ".join(f"{item.label}={_float_text(item.value)}" for item in data.routine_deltas)
    lines = _svg_open(
        figure_id=figure_id,
        width=1200,
        height=920,
        title="Routine perturbation change in macro-category MAE",
        description=(
            "Bars show condition macro-category MAE minus clean final-model MAE. Positive values "
            "are worse. The robustness downgrade threshold is a strict increase above 0.03. "
            f"Exact values: {exact}."
        ),
    )
    lines.append(
        _metadata(
            data,
            figure_id,
            [
                {"delta_macro_category_mae_from_clean": item.value, "condition": item.key}
                for item in data.routine_deltas
            ],
        )
    )
    lines.extend(
        [
            '<text class="title" x="48" y="48">Routine robustness deltas</text>',
            '<text class="subtitle" x="48" y="73">Δ macro-category MAE from clean final-model evaluation · lower is better</text>',
        ]
    )
    plot_left, plot_right, plot_top, plot_bottom = 345.0, 1120.0, 110.0, 794.0
    axis_min, axis_max = -0.012, 0.040

    def x_for(value: float) -> float:
        return plot_left + (value - axis_min) / (axis_max - axis_min) * (plot_right - plot_left)

    for value in (-0.01, 0.0, 0.01, 0.02, 0.03, 0.04):
        x = x_for(value)
        lines.append(
            f'<line class="grid" x1="{_coordinate(x)}" y1="{plot_top}" '
            f'x2="{_coordinate(x)}" y2="{plot_bottom}"/>'
        )
        lines.append(
            f'<text class="tick" text-anchor="middle" x="{_coordinate(x)}" y="817">'
            f"{value:+.2f}</text>"
        )
    zero_x = x_for(0.0)
    gate_x = x_for(ROUTINE_DOWNGRADE_THRESHOLD)
    lines.append(
        f'<line class="axis-line" x1="{_coordinate(zero_x)}" y1="{plot_top}" '
        f'x2="{_coordinate(zero_x)}" y2="{plot_bottom}"/>'
    )
    lines.append(
        f'<line x1="{_coordinate(gate_x)}" y1="{plot_top}" x2="{_coordinate(gate_x)}" '
        f'y2="{plot_bottom}" stroke="#b91c1c" stroke-width="2" stroke-dasharray="8 6">'
        "<title>Robustness downgrade line: +0.03</title></line>"
    )
    lines.append(
        f'<text class="value" text-anchor="middle" x="{_coordinate(gate_x)}" y="98" '
        'fill="#991b1b">downgrade line +0.03</text>'
    )
    row_height = 50.0
    for index, item in enumerate(data.routine_deltas):
        y = plot_top + index * row_height + 9
        value_x = x_for(item.value)
        x = min(zero_x, value_x)
        width = max(abs(value_x - zero_x), 1.0)
        color = "#b91c1c" if item.value > ROUTINE_DOWNGRADE_THRESHOLD else "#0f766e"
        lines.append(
            f'<text class="axis" text-anchor="end" x="329" y="{_coordinate(y + 22)}">'
            f"{_xml(item.label)}</text>"
        )
        lines.append(
            f'<rect x="{_coordinate(x)}" y="{_coordinate(y)}" width="{_coordinate(width)}" '
            f'height="31" rx="3" fill="{color}" data-condition="{_xml(item.key)}" '
            f'data-value="{_float_text(item.value)}"><title>{_xml(item.label)}: Δ MAE '
            f"{_float_text(item.value)}</title></rect>"
        )
        label_x = value_x + (8.0 if item.value >= 0.0 else -8.0)
        anchor = "start" if item.value >= 0.0 else "end"
        lines.append(
            f'<text class="value" text-anchor="{anchor}" x="{_coordinate(label_x)}" '
            f'y="{_coordinate(y + 21)}">{item.value:+.3f}</text>'
        )
    lines.extend(
        [
            '<text class="axis" text-anchor="middle" x="733" y="856">Change in macro-category MAE from clean</text>',
            '<rect x="48" y="883" width="14" height="14" rx="2" fill="#0f766e"/>',
            '<text class="note" x="70" y="895">does not cross threshold</text>',
            '<rect x="265" y="883" width="14" height="14" rx="2" fill="#b91c1c"/>',
            '<text class="note" x="287" y="895">strictly above +0.03</text>',
            _source_footer(data, x=812, y=895),
        ]
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _write_immutable_idempotent(path: Path, content: str) -> None:
    encoded = content.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != encoded:
            raise DataIntegrityError(f"Refusing to overwrite divergent Gate C figure: {path}")
        return
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError:
        if not path.is_file() or path.is_symlink() or path.read_bytes() != encoded:
            raise DataIntegrityError(
                f"Gate C figure appeared concurrently with different bytes: {path}"
            ) from None


def generate_gate_c_figures(
    *,
    results_path: str | Path,
    robustness_path: str | Path,
    run_descriptor_path: str | Path,
    output_directory: str | Path,
) -> tuple[Path, ...]:
    """Validate frozen evidence and create the four immutable SVG figures."""

    data = load_gate_c_figure_data(
        results_path=results_path,
        robustness_path=robustness_path,
        run_descriptor_path=run_descriptor_path,
    )
    rendered = (
        (FIGURE_FILENAMES["workload_macro_mae"], render_workload_macro_mae(data)),
        (FIGURE_FILENAMES["category_scatter"], render_category_scatter(data)),
        (FIGURE_FILENAMES["target_slices"], render_target_slices(data)),
        (FIGURE_FILENAMES["robustness_delta"], render_robustness_delta(data)),
    )
    output = Path(output_directory)
    paths: list[Path] = []
    for filename, content in rendered:
        path = output / filename
        _write_immutable_idempotent(path, content)
        paths.append(path)
    return tuple(paths)
