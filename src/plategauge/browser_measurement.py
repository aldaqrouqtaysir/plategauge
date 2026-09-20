"""Collection and validation of real local browser benchmark measurements."""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .data import sha256_file
from .errors import DataIntegrityError
from .release_artifacts import read_json_object, write_immutable_json
from .release_staging import (
    ValidatedReleaseInputs,
    build_web_release_manifest,
    validate_release_inputs,
)

OBSERVATION_SCHEMA_VERSION = "1.1"
MINIMUM_WARMUPS = 3
MINIMUM_MEASUREMENTS = 20
ALLOWED_BROWSER_CHANNELS = frozenset({"chrome", "msedge", "chromium"})
ALLOWED_BROWSER_MODES = frozenset({"headed", "headless"})
MEMORY_METHOD = "performance.measureUserAgentSpecificMemory"
FIXED_BENCHMARK_SAMPLE_ID = "lefood-0192"

OBSERVATION_KEYS = {
    "schema_version",
    "kind",
    "measured_at",
    "browser_name",
    "browser_version",
    "browser_mode",
    "onnxruntime_web_version",
    "manufacturer_model",
    "cpu",
    "ram_gb",
    "operating_system",
    "warmup_runs",
    "warm_inference_ms",
    "first_load_bytes",
    "peak_application_memory_mb",
    "memory_measurement_method",
    "memory_measurement_notes",
    "fixed_sample_id",
    "fixed_before_sha256",
    "fixed_after_sha256",
    "numeric_prediction_recorded",
}

ObservationRunner = Callable[[Sequence[str], Path, int], Mapping[str, Any]]


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataIntegrityError(f"{label} must be a non-empty string")
    return value.strip()


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataIntegrityError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise DataIntegrityError(f"{label} must be finite and greater than zero")
    return number


def _positive_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DataIntegrityError(f"{label} must be a positive integer")
    return value


def _sha256_digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DataIntegrityError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_built_benchmark_sample(
    *,
    web_root: Path,
    sample_id: str,
    before_sha256: str,
    after_sha256: str,
) -> None:
    """Bind the browser-reported pair hashes to the exact static-build bytes."""

    if sample_id != FIXED_BENCHMARK_SAMPLE_ID:
        raise DataIntegrityError(
            f"Browser benchmark must use fixed sample {FIXED_BENCHMARK_SAMPLE_ID}"
        )
    for role, expected_sha256 in (
        ("before", before_sha256),
        ("after", after_sha256),
    ):
        path = web_root / "examples" / f"{sample_id}-{role}.jpg"
        if not path.is_file() or path.is_symlink():
            raise DataIntegrityError(
                f"Built benchmark {role} asset is missing or not a regular file: {path}"
            )
        if sha256_file(path) != expected_sha256:
            raise DataIntegrityError(
                f"Browser-reported {role} asset hash differs from the static-build bytes"
            )


def validate_built_release(
    *,
    web_root: str | Path,
    release_inputs: ValidatedReleaseInputs,
) -> str:
    """Verify that a static build embeds the exact validated staged release."""

    root = Path(web_root)
    if not root.is_dir() or root.is_symlink():
        raise DataIntegrityError(f"Built web root must be a regular directory: {root}")
    index = root / "index.html"
    model = root / "models" / "plategauge.onnx"
    manifest_path = root / "models" / "release.json"
    for label, path in (("index", index), ("model", model), ("manifest", manifest_path)):
        if not path.is_file() or path.is_symlink():
            raise DataIntegrityError(f"Built web {label} is missing or not a regular file: {path}")
    if (
        model.stat().st_size != release_inputs.model_size_bytes
        or sha256_file(model) != release_inputs.model_sha256
    ):
        raise DataIntegrityError("Built web model differs from the frozen ONNX bytes")
    manifest = read_json_object(manifest_path)
    model_version = manifest.get("modelVersion")
    if not isinstance(model_version, str):
        raise DataIntegrityError("Built web manifest lacks modelVersion")
    expected = build_web_release_manifest(release_inputs, model_version=model_version)
    if manifest != expected:
        raise DataIntegrityError("Built web manifest differs from frozen release evidence")
    ort_assets = list((root / "ort").glob("*.wasm"))
    if not ort_assets or any(path.is_symlink() or not path.is_file() for path in ort_assets):
        raise DataIntegrityError("Built web release lacks regular ONNX Runtime WASM assets")
    return model_version


def _default_observation_runner(
    command: Sequence[str], working_directory: Path, timeout_seconds: int
) -> Mapping[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=working_directory,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DataIntegrityError(f"Browser observation could not complete: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
        raise DataIntegrityError(f"Browser observation failed: {detail[:2000]}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise DataIntegrityError("Browser observer did not return one JSON object") from exc
    if not isinstance(value, dict):
        raise DataIntegrityError("Browser observer output must be a JSON object")
    return cast(dict[str, Any], value)


def compose_browser_measurement(
    *,
    observation: Mapping[str, Any],
    release_inputs: ValidatedReleaseInputs,
    device_label: str,
    physical_device_confirmed: bool,
) -> dict[str, Any]:
    """Convert a genuine observer record into the frozen measurement schema."""

    if set(observation) != OBSERVATION_KEYS:
        raise DataIntegrityError(
            f"Browser observation fields differ from schema {OBSERVATION_SCHEMA_VERSION}"
        )
    if (
        observation.get("schema_version") != OBSERVATION_SCHEMA_VERSION
        or observation.get("kind") != "physical_browser_observation"
    ):
        raise DataIntegrityError("Browser observation identity is invalid")
    if physical_device_confirmed is not True:
        raise DataIntegrityError("A physical reference device must be explicitly confirmed")
    measured_at = _nonempty(observation.get("measured_at"), "measured_at")
    try:
        parsed_timestamp = datetime.fromisoformat(measured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataIntegrityError("measured_at must be an ISO-8601 timestamp") from exc
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
        raise DataIntegrityError("measured_at must include a timezone")

    warmups = _positive_integer(observation.get("warmup_runs"), "warmup_runs")
    if warmups < MINIMUM_WARMUPS:
        raise DataIntegrityError(f"At least {MINIMUM_WARMUPS} warmup runs are required")
    warm = observation.get("warm_inference_ms")
    if not isinstance(warm, list) or len(warm) < MINIMUM_MEASUREMENTS:
        raise DataIntegrityError(
            f"At least {MINIMUM_MEASUREMENTS} warm inference measurements are required"
        )
    timings = [_positive_number(value, "warm_inference_ms item") for value in warm]
    first_load = _positive_integer(observation.get("first_load_bytes"), "first_load_bytes")
    peak_memory = _positive_number(
        observation.get("peak_application_memory_mb"), "peak_application_memory_mb"
    )
    memory_method = observation.get("memory_measurement_method")
    if memory_method != MEMORY_METHOD:
        raise DataIntegrityError(
            "Browser observer must use performance.measureUserAgentSpecificMemory"
        )
    browser_mode = observation.get("browser_mode")
    if browser_mode not in ALLOWED_BROWSER_MODES:
        raise DataIntegrityError("browser_mode must be exactly 'headed' or 'headless'")
    sample_id = _nonempty(observation.get("fixed_sample_id"), "fixed_sample_id")
    if sample_id != FIXED_BENCHMARK_SAMPLE_ID:
        raise DataIntegrityError(
            f"Browser benchmark must use fixed sample {FIXED_BENCHMARK_SAMPLE_ID}"
        )
    before_sha256 = _sha256_digest(observation.get("fixed_before_sha256"), "fixed_before_sha256")
    after_sha256 = _sha256_digest(observation.get("fixed_after_sha256"), "fixed_after_sha256")
    if observation.get("numeric_prediction_recorded") is not False:
        raise DataIntegrityError("Browser benchmark evidence must not record a numeric prediction")

    return {
        "schema_version": "1.0",
        "kind": "browser_benchmark_measurement",
        "status": "measured",
        "model_sha256": release_inputs.model_sha256,
        "release_evidence_sha256": release_inputs.evidence_file_sha256,
        "measured_at": measured_at,
        "benchmark_input": {
            "kind": "fixed_bundled_pair",
            "sample_id": sample_id,
            "before_asset_sha256": before_sha256,
            "after_asset_sha256": after_sha256,
            "numeric_prediction_recorded": False,
        },
        "reference_device": {
            "label": _nonempty(device_label, "device_label"),
            "manufacturer_model": _nonempty(
                observation.get("manufacturer_model"), "manufacturer_model"
            ),
            "cpu": _nonempty(observation.get("cpu"), "cpu"),
            "ram_gb": _positive_number(observation.get("ram_gb"), "ram_gb"),
            "operating_system": _nonempty(observation.get("operating_system"), "operating_system"),
            "physical_device": True,
        },
        "runtime": {
            "browser_name": _nonempty(observation.get("browser_name"), "browser_name"),
            "browser_version": _nonempty(observation.get("browser_version"), "browser_version"),
            "browser_mode": browser_mode,
            "onnxruntime_web_version": _nonempty(
                observation.get("onnxruntime_web_version"), "onnxruntime_web_version"
            ),
            "execution_provider": "wasm",
            "wasm_threads": 1,
            "webgpu_enabled": False,
            "build_source": "local_static_build",
        },
        "measurements": {
            "warmup_runs": warmups,
            "warm_inference_ms": timings,
            "first_load_bytes": first_load,
            "peak_application_memory_mb": peak_memory,
            "memory_measurement_method": memory_method,
            "memory_measurement_notes": _nonempty(
                observation.get("memory_measurement_notes"), "memory_measurement_notes"
            ),
        },
    }


def collect_browser_measurement(
    *,
    evidence_path: str | Path,
    results_path: str | Path,
    web_root: str | Path,
    observer_script: str | Path,
    output_path: str | Path,
    device_label: str,
    physical_device_confirmed: bool,
    warmups: int = MINIMUM_WARMUPS,
    measurements: int = MINIMUM_MEASUREMENTS,
    browser_channel: str = "chrome",
    headless: bool = False,
    base_path: str = "/plategauge/",
    node_binary: str = "node",
    timeout_seconds: int = 1800,
    observation_runner: ObservationRunner = _default_observation_runner,
) -> dict[str, Any]:
    """Run the local static app and immutably record genuine browser evidence."""

    if physical_device_confirmed is not True:
        raise DataIntegrityError("A physical reference device must be explicitly confirmed")
    if warmups < MINIMUM_WARMUPS or measurements < MINIMUM_MEASUREMENTS:
        raise DataIntegrityError(
            "Requested warmup or measurement count is below the frozen minimum"
        )
    if browser_channel not in ALLOWED_BROWSER_CHANNELS:
        raise DataIntegrityError("Unsupported browser channel")
    if not base_path.startswith("/") or not base_path.endswith("/") or ".." in base_path:
        raise DataIntegrityError("base_path must be an absolute, traversal-free URL path")
    if timeout_seconds < 1:
        raise DataIntegrityError("timeout_seconds must be positive")
    output = Path(output_path)
    if output.exists() or output.is_symlink():
        raise DataIntegrityError(f"Immutable browser measurement already exists: {output}")

    inputs = validate_release_inputs(evidence_path=evidence_path, results_path=results_path)
    root = Path(web_root).resolve()
    validate_built_release(web_root=root, release_inputs=inputs)
    script = Path(observer_script).resolve()
    if not script.is_file() or script.is_symlink():
        raise DataIntegrityError(f"Browser observer script must be a regular file: {script}")
    command = [
        node_binary,
        str(script),
        "--web-root",
        str(root),
        "--base-path",
        base_path,
        "--warmups",
        str(warmups),
        "--measurements",
        str(measurements),
        "--browser-channel",
        browser_channel,
    ]
    if headless:
        command.append("--headless")
    observation = observation_runner(command, script.parent.parent, timeout_seconds)
    measurement = compose_browser_measurement(
        observation=observation,
        release_inputs=inputs,
        device_label=device_label,
        physical_device_confirmed=physical_device_confirmed,
    )
    expected_browser_mode = "headless" if headless else "headed"
    if measurement["runtime"]["browser_mode"] != expected_browser_mode:
        raise DataIntegrityError(
            "Browser observer mode differs from the requested headed/headless launch mode"
        )
    benchmark_input = measurement["benchmark_input"]
    _validate_built_benchmark_sample(
        web_root=root,
        sample_id=benchmark_input["sample_id"],
        before_sha256=benchmark_input["before_asset_sha256"],
        after_sha256=benchmark_input["after_asset_sha256"],
    )
    write_immutable_json(output, measurement)
    return measurement
