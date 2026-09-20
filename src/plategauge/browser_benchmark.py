"""Validate real browser measurements and evaluate the frozen browser gate."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from .data import sha256_file
from .errors import DataIntegrityError
from .release_artifacts import canonical_json_sha256, read_json_object, write_immutable_json

BROWSER_BENCHMARK_SCHEMA_VERSION = "1.0"
MINIMUM_WARM_MEASUREMENTS = 20
MAXIMUM_WARM_P95_MS = 1500.0
MAXIMUM_PEAK_MEMORY_MB = 512.0
ALLOWED_MEMORY_METHODS = frozenset(
    {
        "browser_process_rss",
        "performance.measureUserAgentSpecificMemory",
        "os_process_monitor",
    }
)


def _sha(value: Any, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise DataIntegrityError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _positive_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DataIntegrityError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise DataIntegrityError(f"{label} must be finite and greater than zero")
    return number


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataIntegrityError(f"{label} must be a non-empty string")
    return value.strip()


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values or not 0 < percentile <= 1:
        raise ValueError("Nearest-rank percentile requires values and p in (0,1]")
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def evaluate_browser_measurement(
    measurement: Mapping[str, Any],
    *,
    measurement_sha256: str,
    expected_model_sha256: str,
    expected_release_evidence_sha256: str,
) -> dict[str, Any]:
    """Validate supplied measurements and compute gates without inventing values."""

    if measurement.get("schema_version") != BROWSER_BENCHMARK_SCHEMA_VERSION:
        raise DataIntegrityError("Unsupported browser benchmark measurement schema")
    if measurement.get("kind") != "browser_benchmark_measurement":
        raise DataIntegrityError("Unexpected browser benchmark measurement kind")
    if measurement.get("status") != "measured":
        raise DataIntegrityError("Browser gates require a real status='measured' record")
    _sha(measurement_sha256, "measurement_sha256")
    model_sha = _sha(measurement.get("model_sha256"), "measurement.model_sha256")
    evidence_sha = _sha(
        measurement.get("release_evidence_sha256"),
        "measurement.release_evidence_sha256",
    )
    if model_sha != _sha(expected_model_sha256, "expected_model_sha256"):
        raise DataIntegrityError("Browser measurement is bound to different ONNX bytes")
    if evidence_sha != _sha(expected_release_evidence_sha256, "expected_release_evidence_sha256"):
        raise DataIntegrityError("Browser measurement is bound to different release evidence")

    measured_at = _nonempty(measurement.get("measured_at"), "measured_at")
    try:
        timestamp = datetime.fromisoformat(measured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataIntegrityError("measured_at must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None:
        raise DataIntegrityError("measured_at must include a timezone")

    device = measurement.get("reference_device")
    runtime = measurement.get("runtime")
    values = measurement.get("measurements")
    if (
        not isinstance(device, dict)
        or not isinstance(runtime, dict)
        or not isinstance(values, dict)
    ):
        raise DataIntegrityError("Browser measurement requires device, runtime, and measurements")
    if device.get("physical_device") is not True:
        raise DataIntegrityError("Reference-laptop claims require a physical device measurement")
    for key in ("label", "manufacturer_model", "cpu", "operating_system"):
        _nonempty(device.get(key), f"reference_device.{key}")
    _positive_number(device.get("ram_gb"), "reference_device.ram_gb")

    for key in ("browser_name", "browser_version", "onnxruntime_web_version"):
        _nonempty(runtime.get(key), f"runtime.{key}")
    if runtime.get("execution_provider") != "wasm":
        raise DataIntegrityError("Browser benchmark must use the release WASM execution provider")
    if runtime.get("wasm_threads") != 1 or runtime.get("webgpu_enabled") is not False:
        raise DataIntegrityError("Browser benchmark must use single-threaded WASM with WebGPU off")
    if runtime.get("build_source") not in {"local_static_build", "github_pages"}:
        raise DataIntegrityError("runtime.build_source is outside the documented release matrix")

    warm = values.get("warm_inference_ms")
    if not isinstance(warm, list) or len(warm) < MINIMUM_WARM_MEASUREMENTS:
        raise DataIntegrityError(
            f"At least {MINIMUM_WARM_MEASUREMENTS} warm inference measurements are required"
        )
    warm_values = [_positive_number(value, "warm_inference_ms item") for value in warm]
    warmup_runs = values.get("warmup_runs")
    if not isinstance(warmup_runs, int) or isinstance(warmup_runs, bool) or warmup_runs < 3:
        raise DataIntegrityError("At least three unreported warmup runs are required")
    first_load_bytes = values.get("first_load_bytes")
    if (
        not isinstance(first_load_bytes, int)
        or isinstance(first_load_bytes, bool)
        or first_load_bytes < 1
    ):
        raise DataIntegrityError(
            "first_load_bytes must be a positive integer measured from transfer data"
        )
    peak_memory = _positive_number(
        values.get("peak_application_memory_mb"), "peak_application_memory_mb"
    )
    memory_method = values.get("memory_measurement_method")
    if memory_method not in ALLOWED_MEMORY_METHODS:
        raise DataIntegrityError("memory_measurement_method is unsupported or undocumented")
    _nonempty(values.get("memory_measurement_notes"), "memory_measurement_notes")

    p50 = _nearest_rank(warm_values, 0.50)
    p95 = _nearest_rank(warm_values, 0.95)
    latency_passed = p95 <= MAXIMUM_WARM_P95_MS
    memory_passed = peak_memory <= MAXIMUM_PEAK_MEMORY_MB
    core: dict[str, Any] = {
        "schema_version": BROWSER_BENCHMARK_SCHEMA_VERSION,
        "kind": "browser_benchmark_gate",
        "status": "passed" if latency_passed and memory_passed else "failed",
        "source_measurement_sha256": measurement_sha256,
        "model_sha256": model_sha,
        "release_evidence_sha256": evidence_sha,
        "measured_at": measured_at,
        "reference_device": dict(device),
        "runtime": dict(runtime),
        "reported": {
            "warmup_runs": warmup_runs,
            "warm_measurement_count": len(warm_values),
            "first_load_bytes": first_load_bytes,
            "peak_application_memory_mb": peak_memory,
            "memory_measurement_method": memory_method,
            "memory_measurement_notes": values["memory_measurement_notes"],
        },
        "derived": {
            "percentile_method": "nearest-rank",
            "warm_p50_ms": p50,
            "warm_p95_ms": p95,
        },
        "gates": {
            "warm_p95": {
                "observed_ms": p95,
                "maximum_ms": MAXIMUM_WARM_P95_MS,
                "passed": latency_passed,
            },
            "peak_application_memory": {
                "observed_mb": peak_memory,
                "maximum_mb": MAXIMUM_PEAK_MEMORY_MB,
                "passed": memory_passed,
            },
            "all_passed": latency_passed and memory_passed,
        },
        "claim_limits": {
            "reference_device_only": True,
            "phone_performance_claim_allowed": False,
            "unmeasured_browser_claim_allowed": False,
        },
    }
    return core | {"evidence_sha256": canonical_json_sha256(core)}


def evaluate_browser_benchmark_files(
    *,
    measurement_path: str | Path,
    model_path: str | Path,
    release_evidence_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Read real inputs, verify byte bindings, and create one immutable gate report."""

    measurement_file = Path(measurement_path)
    model_file = Path(model_path)
    evidence_file = Path(release_evidence_path)
    for label, path in (
        ("measurement", measurement_file),
        ("model", model_file),
        ("release evidence", evidence_file),
    ):
        if not path.is_file():
            raise DataIntegrityError(f"Browser benchmark {label} file is missing: {path}")
    measurement = read_json_object(measurement_file)
    report = evaluate_browser_measurement(
        measurement,
        measurement_sha256=sha256_file(measurement_file),
        expected_model_sha256=sha256_file(model_file),
        expected_release_evidence_sha256=sha256_file(evidence_file),
    )
    write_immutable_json(output_path, report)
    return report
