"""Fail-closed loading of the frozen final deployment checkpoint.

Release tooling must not infer a model configuration from a checkpoint or
silently rebuild a selection.  This module binds the final checkpoint to the
approved protocol, the five inner-only outer selections, the immutable task
record, and the experiment run identity before any model bytes are loaded.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data import sha256_file
from .errors import DataIntegrityError, missing_extra
from .orchestration import WorkloadResult, build_final_task, protocol_preflight
from .training import MODEL_CONFIGURATIONS

RELEASE_ARTIFACT_SCHEMA_VERSION = "1.0"
FINAL_TASK_ID = "final.deploy.paired_mobilenet"
FINAL_TASK_RELATIVE_DIRECTORY = Path("tasks") / FINAL_TASK_ID
EXPECTED_VALID_PAIRS = 514
EXPECTED_OUTER_FOLDS = frozenset(range(5))


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize evidence deterministically and reject non-finite floats."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DataIntegrityError(f"Evidence is not canonical JSON: {exc}") from exc


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def read_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataIntegrityError(f"Cannot read JSON object {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise DataIntegrityError(f"Expected a JSON object at {source}")
    return value


def write_immutable_json(path: str | Path, value: Mapping[str, Any]) -> None:
    """Create, never replace, a canonical human-readable JSON artifact."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Validate canonicalizability before creating a file.
    canonical_json_bytes(dict(value))
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                dict(value),
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            handle.write("\n")
    except FileExistsError as exc:
        raise DataIntegrityError(f"Immutable artifact already exists: {destination}") from exc


def _require_sha256(value: Any, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise DataIntegrityError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _safe_artifact_path(task_directory: Path, value: Any) -> Path:
    relative = Path(str(value))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise DataIntegrityError("Final checkpoint artifact path is unsafe")
    candidate = task_directory / relative
    if candidate.is_symlink() or not candidate.is_file():
        raise DataIntegrityError(f"Final checkpoint artifact is missing: {candidate}")
    try:
        candidate.resolve().relative_to(task_directory.resolve())
    except ValueError as exc:
        raise DataIntegrityError("Final checkpoint artifact escaped its task directory") from exc
    return candidate


def _number(value: Any, label: str, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DataIntegrityError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise DataIntegrityError(f"{label} must be finite and in [{minimum}, {maximum}]")
    return number


def _validate_selection_source_hashes(
    experiment_directory: Path,
    selection: Mapping[str, Any],
) -> None:
    sources = selection.get("sources")
    if not isinstance(sources, list) or not sources:
        raise DataIntegrityError("Outer selection must bind its inner task results")
    seen: set[str] = set()
    for item in sources:
        if not isinstance(item, dict):
            raise DataIntegrityError("Outer selection source entries must be objects")
        task_id = item.get("task_id")
        if not isinstance(task_id, str) or not task_id or task_id in seen:
            raise DataIntegrityError("Outer selection task sources must be unique")
        seen.add(task_id)
        source = experiment_directory / "tasks" / task_id / "result.json"
        if not source.is_file() or sha256_file(source) != _require_sha256(
            item.get("sha256"), "outer selection source hash"
        ):
            raise DataIntegrityError(f"Outer selection source hash mismatch: {task_id}")


def _validate_final_selection(
    experiment_directory: Path,
    protocol_id: str,
) -> tuple[dict[str, Any], Path]:
    final_path = experiment_directory / "selections" / "final.json"
    final = read_json_object(final_path)
    expected_identity = {
        "schema_version": "1.0",
        "kind": "final_deploy_choice",
        "information_boundary": "inner_selections_only_no_outer_metrics",
        "protocol_id": protocol_id,
    }
    for key, expected in expected_identity.items():
        if final.get(key) != expected:
            raise DataIntegrityError(f"Final selection {key!r} differs from {expected!r}")

    source_entries = final.get("outer_selection_sources")
    if not isinstance(source_entries, list) or len(source_entries) != 5:
        raise DataIntegrityError("Final selection must bind exactly five outer selections")
    outer: list[dict[str, Any]] = []
    observed_folds: set[int] = set()
    for item in source_entries:
        if not isinstance(item, dict) or not isinstance(item.get("outer_fold"), int):
            raise DataIntegrityError("Malformed final outer-selection source")
        fold = int(item["outer_fold"])
        if fold in observed_folds:
            raise DataIntegrityError("Final selection repeats an outer fold")
        observed_folds.add(fold)
        path = experiment_directory / "selections" / f"outer-{fold}.json"
        if not path.is_file() or sha256_file(path) != _require_sha256(
            item.get("sha256"), "outer selection hash"
        ):
            raise DataIntegrityError(f"Final selection source hash mismatch for fold {fold}")
        payload = read_json_object(path)
        if (
            payload.get("schema_version") != "1.0"
            or payload.get("kind") != "outer_selection"
            or payload.get("information_boundary") != "inner_development_predictions_only"
            or payload.get("protocol_id") != protocol_id
            or payload.get("outer_fold") != fold
        ):
            raise DataIntegrityError(f"Malformed outer selection for fold {fold}")
        _validate_selection_source_hashes(experiment_directory, payload)
        outer.append(payload)
    if observed_folds != EXPECTED_OUTER_FOLDS:
        raise DataIntegrityError("Final selection must cover outer folds 0 through 4")

    configurations: list[str] = []
    epochs: list[int] = []
    policy_records: list[dict[str, Any]] = []
    for payload in outer:
        primary = payload.get("primary")
        policy = payload.get("uncertainty_policy")
        if not isinstance(primary, dict) or not isinstance(policy, dict):
            raise DataIntegrityError("Outer selection lacks primary or uncertainty selection")
        configuration = str(primary.get("configuration"))
        epoch = primary.get("epoch")
        if (
            configuration not in MODEL_CONFIGURATIONS
            or not isinstance(epoch, int)
            or not 1 <= epoch <= 80
        ):
            raise DataIntegrityError("Outer primary selection is outside the frozen search space")
        configurations.append(configuration)
        epochs.append(epoch)
        policy_records.append(
            {
                "outer_fold": int(payload["outer_fold"]),
                "selected_primary_configuration": configuration,
                "interval_correction": _number(
                    policy.get("interval_correction"), "interval correction"
                ),
                "abstention_threshold": _number(
                    policy.get("abstention_threshold"), "abstention threshold"
                ),
            }
        )

    counts = {name: configurations.count(name) for name in MODEL_CONFIGURATIONS}
    expected_configuration = min(
        ("M1", "M2"), key=lambda name: (-counts[name], 0 if name == "M1" else 1)
    )
    expected_epoch = int(statistics.median(epochs))
    included = [
        record
        for record in sorted(policy_records, key=lambda value: int(value["outer_fold"]))
        if record["selected_primary_configuration"] == expected_configuration
    ]
    excluded = [
        {
            "outer_fold": record["outer_fold"],
            "selected_primary_configuration": record["selected_primary_configuration"],
        }
        for record in sorted(policy_records, key=lambda value: int(value["outer_fold"]))
        if record["selected_primary_configuration"] != expected_configuration
    ]
    if len(included) < 3:
        raise DataIntegrityError("Final configuration has fewer than three matching policies")
    final_policy = final.get("uncertainty_policy")
    if not isinstance(final_policy, dict):
        raise DataIntegrityError("Final uncertainty policy is malformed")
    expected_policy = {
        "method": "median_of_inner_only_outer_policies_matching_final_configuration",
        "selection_rule": (
            "include_only_outer_selections_whose_selected_primary_configuration_"
            "matches_the_final_modal_configuration"
        ),
        "final_configuration": expected_configuration,
        "minimum_matching_outer_selections": 3,
        "included_outer_selections": included,
        "excluded_outer_selections": excluded,
        "interval_correction": float(
            statistics.median(float(record["interval_correction"]) for record in included)
        ),
        "abstention_threshold": float(
            statistics.median(float(record["abstention_threshold"]) for record in included)
        ),
    }
    if (
        final.get("configuration") != expected_configuration
        or final.get("epoch") != expected_epoch
        or final_policy != expected_policy
    ):
        raise DataIntegrityError("Final selection does not reproduce the frozen inner-only rule")
    return final, final_path


@dataclass(frozen=True, slots=True)
class _RecordedRunner:
    """Read-only runner identity used to replay orchestration validation."""

    fingerprint: str

    def execute(self, request: Any, workspace: Path) -> WorkloadResult:  # pragma: no cover
        raise AssertionError("Release validation must never execute a workload")


@dataclass(frozen=True, slots=True)
class FrozenFinalArtifact:
    """Validated identities required to load or export the final model."""

    experiment_directory: Path
    protocol_id: str
    run_id: str
    runner_fingerprint: str
    configuration: str
    epoch: int
    dropout: float
    interval_correction: float
    abstention_threshold: float
    manifest_path: Path
    checkpoint_path: Path
    hashes: dict[str, str]
    checkpoint_size_bytes: int

    def evidence_identity(self) -> dict[str, Any]:
        return {
            "schema_version": RELEASE_ARTIFACT_SCHEMA_VERSION,
            "protocol_id": self.protocol_id,
            "run_id": self.run_id,
            "runner_fingerprint": self.runner_fingerprint,
            "configuration": self.configuration,
            "epoch": self.epoch,
            "dropout": self.dropout,
            "uncertainty_policy": {
                "interval_correction": self.interval_correction,
                "abstention_threshold": self.abstention_threshold,
            },
            "checkpoint_size_bytes": self.checkpoint_size_bytes,
            "hashes": dict(sorted(self.hashes.items())),
        }


def validate_frozen_final_artifact(
    *,
    experiment_directory: str | Path,
    audit_report_path: str | Path,
    manifest_path: str | Path,
    config_path: str | Path,
    folds_path: str | Path,
) -> FrozenFinalArtifact:
    """Validate the full outcome-independent and final-training evidence chain."""

    experiment = Path(experiment_directory)
    if not experiment.is_dir():
        raise DataIntegrityError(f"Experiment directory is missing: {experiment}")
    preflight, protocol = protocol_preflight(
        audit_report_path=audit_report_path,
        manifest_path=manifest_path,
        config_path=config_path,
        folds_path=folds_path,
    )
    if preflight.status != "ready" or protocol is None:
        raise DataIntegrityError(f"Frozen protocol is blocked: {preflight.blocker}")

    run_path = experiment / "run.json"
    run = read_json_object(run_path)
    run_id = _require_sha256(run.get("run_id"), "run_id")
    run_core = {key: value for key, value in run.items() if key != "run_id"}
    if canonical_json_sha256(run_core) != run_id:
        raise DataIntegrityError("Experiment run_id does not match its canonical descriptor")
    run_protocol = run.get("protocol")
    if not isinstance(run_protocol, dict):
        raise DataIntegrityError("Experiment run lacks a protocol descriptor")
    if run_protocol.get("protocol_id") != protocol.protocol_id:
        raise DataIntegrityError("Experiment run uses a different frozen protocol")
    if run_protocol.get("input_hashes") != dict(sorted(protocol.input_hashes.items())):
        raise DataIntegrityError("Experiment run protocol input hashes changed")
    runner_fingerprint = _require_sha256(run.get("runner_fingerprint"), "runner fingerprint")

    final, final_path = _validate_final_selection(experiment, protocol.protocol_id)
    configuration = str(final["configuration"])
    epoch = int(final["epoch"])
    policy = final["uncertainty_policy"]
    assert isinstance(policy, dict)

    task_directory = experiment / FINAL_TASK_RELATIVE_DIRECTORY
    task_path = task_directory / "task.json"
    result_path = task_directory / "result.json"
    task = read_json_object(task_path)
    result = read_json_object(result_path)
    # Reconstructing through orchestration validates every inner selection,
    # source artifact, tuned parameter, full final parameter dictionary, and
    # the D014 matching-configuration uncertainty policy. A coordinated edit
    # to task.json/result.json therefore cannot authorize a different recipe.
    canonical_task = build_final_task(
        protocol,
        experiment,
        _RecordedRunner(runner_fingerprint),
    ).to_dict()
    # ``TaskSpec.to_dict()`` intentionally preserves tuples for sequence fields,
    # while the persisted JSON representation necessarily reloads them as
    # lists.  Compare the canonical JSON representation rather than Python
    # container identity so semantically identical persisted tasks validate.
    if canonical_json_sha256(task) != canonical_json_sha256(canonical_task):
        raise DataIntegrityError("Final task differs from the canonically reconstructed recipe")
    parameters = task.get("parameters")
    if not isinstance(parameters, dict):
        raise DataIntegrityError("Final task parameters are malformed")
    if (
        parameters.get("configuration") != configuration
        or parameters.get("epoch") != epoch
        or parameters.get("training_scope") != "all_514_valid_pairs"
        or parameters.get("selection_source") != "inner_only_modal_configuration_and_median_epoch"
        or parameters.get("uncertainty_policy") != policy
    ):
        raise DataIntegrityError("Final task is not bound to the frozen final selection")

    try:
        config = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DataIntegrityError(f"Cannot read frozen experiment config: {exc}") from exc
    config_table = config.get("configuration")
    if not isinstance(config_table, dict) or not isinstance(config_table.get(configuration), dict):
        raise DataIntegrityError("Frozen configuration table is malformed")
    dropout = _number(
        config_table[configuration].get("dropout"),
        "selected dropout",
        minimum=0.0,
        maximum=0.99,
    )
    if float(parameters.get("dropout", -1.0)) != dropout:
        raise DataIntegrityError(
            "Final task dropout differs from the frozen selected configuration"
        )

    expected_result_identity = {
        "schema_version": "1.0",
        "status": "complete",
        "task_id": FINAL_TASK_ID,
        "protocol_id": protocol.protocol_id,
        "task_spec_sha256": canonical_json_sha256(task),
        "runner_fingerprint": runner_fingerprint,
    }
    for key, expected in expected_result_identity.items():
        if result.get(key) != expected:
            raise DataIntegrityError(f"Final task result identity mismatch: {key}")
    payload = result.get("payload")
    if payload != {"training_count": EXPECTED_VALID_PAIRS}:
        raise DataIntegrityError("Final task payload differs from the 514-pair training contract")
    if result.get("payload_sha256") != canonical_json_sha256(payload):
        raise DataIntegrityError("Final task payload hash mismatch")
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict):
        raise DataIntegrityError("Final task must declare exactly one checkpoint artifact")
    inventory = artifacts[0]
    if inventory.get("role") != "model_checkpoint":
        raise DataIntegrityError("Final task artifact role must be model_checkpoint")
    checkpoint = _safe_artifact_path(task_directory, inventory.get("path"))
    checkpoint_hash = sha256_file(checkpoint)
    if (
        inventory.get("size_bytes") != checkpoint.stat().st_size
        or inventory.get("sha256") != checkpoint_hash
    ):
        raise DataIntegrityError("Final model checkpoint hash or size mismatch")

    hashes = {
        "audit_report_sha256": sha256_file(audit_report_path),
        "checkpoint_sha256": checkpoint_hash,
        "experiment_config_sha256": sha256_file(config_path),
        "final_selection_sha256": sha256_file(final_path),
        "folds_sha256": sha256_file(folds_path),
        "manifest_sha256": sha256_file(manifest_path),
        "run_descriptor_sha256": sha256_file(run_path),
        "task_result_sha256": sha256_file(result_path),
        "task_spec_sha256": sha256_file(task_path),
    }
    return FrozenFinalArtifact(
        experiment_directory=experiment.resolve(),
        protocol_id=protocol.protocol_id,
        run_id=run_id,
        runner_fingerprint=runner_fingerprint,
        configuration=configuration,
        epoch=epoch,
        dropout=dropout,
        interval_correction=_number(policy.get("interval_correction"), "interval correction"),
        abstention_threshold=_number(policy.get("abstention_threshold"), "abstention threshold"),
        manifest_path=Path(manifest_path).resolve(),
        checkpoint_path=checkpoint.resolve(),
        hashes=hashes,
        checkpoint_size_bytes=checkpoint.stat().st_size,
    )


def load_frozen_paired_model(artifact: FrozenFinalArtifact, *, device: str = "cpu") -> Any:
    """Load the validated final state without downloading pretrained weights."""

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise missing_extra("Frozen model loading", "train", "torch") from exc
    from .model import build_paired_model

    # pretrained=False is intentional: the final checkpoint contains the full
    # encoder and head state, and release tooling is forbidden from downloading.
    model = build_paired_model(dropout=artifact.dropout, pretrained=False)
    try:
        payload = torch.load(artifact.checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover - torch error classes vary by version
        raise DataIntegrityError(f"Cannot load final checkpoint safely: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("task_id") != FINAL_TASK_ID:
        raise DataIntegrityError("Final checkpoint does not identify the frozen final task")
    state_dict = payload.get("state_dict")
    if not isinstance(state_dict, dict) or not state_dict:
        raise DataIntegrityError("Final checkpoint does not contain a non-empty state_dict")
    try:
        model.load_state_dict(state_dict, strict=True)
        model.eval().to(device)
    except (RuntimeError, ValueError) as exc:
        raise DataIntegrityError(
            f"Final checkpoint does not match the frozen architecture: {exc}"
        ) from exc
    return model
