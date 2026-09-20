"""Portable, fail-closed packaging for the local release-review candidate."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from .data import sha256_file
from .errors import DataIntegrityError
from .release_bundle_audit import audit_release_bundle
from .web_evidence import verify_web_benchmark_evidence

SCHEMA_VERSION = 1
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_MODE = 0o100644
DEFAULT_REVIEW_DELIVERABLES = (
    "PlateGauge_Gate_C_Approval_Record.md",
    "PlateGauge_Application_and_Mastery_Draft_Pack.md",
    "PlateGauge_Gate_D_Technical_Readiness_Memo_DRAFT.md",
    "PlateGauge_Pre_Gate_D_Remediation_Report_2026-09-20.md",
    "PlateGauge_One_Page_Project_Brief_Gate_D_Draft.pdf",
    "PlateGauge_Gate_D_Review_Preview.png",
)
REQUIRED_SOURCE_PATHS = (
    "artifacts/plategauge.onnx",
    "artifacts/plategauge.onnx.evidence.json",
    "configs/web_benchmark_selection.json",
    "data/manifests/lefood_v1_manifest.csv",
    "reports/error_analysis.json",
    "reports/results.json",
    "web/public/models/plategauge.onnx",
    "web/public/models/release.json",
    "web/public/evidence/benchmark-evidence.json",
    "web/src/generated/benchmarkEvidence.json",
)
PRIVATE_OR_LOCAL_PREFIXES = (
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    "artifacts/cache/",
    "artifacts/checkpoints/",
    "artifacts/superseded/",
    "artifacts/tmp/",
    "data/cache/",
    "data/raw/",
    "docs/application/",
    "docs/mastery/",
    "web/coverage/",
    "web/dist/",
    "web/node_modules/",
    "web/playwright-report/",
    "web/public/legal/",
    "web/public/ort/",
    "web/test-results/",
    "work/",
)
PRIVATE_OR_LOCAL_FILES = {
    "docs/AI_ASSISTANCE_LOG.md",
    "docs/APPLICATION_CRITICAL_PATH.md",
    "docs/APPLICATION_TIMELINE.md",
    "docs/CHANGELOG.md",
    "docs/CONSTRAINTS.md",
    "docs/CONTINUATION_PROMPT.md",
    "docs/CONTRIBUTION_RECORD.md",
    "docs/DECISION_LOG.md",
    "docs/FINAL_AUDIT.md",
    "docs/FINALIST_COMPARISON.md",
    "docs/IDEA_LONG_LIST.md",
    "docs/IDEA_SCORECARD.csv",
    "docs/MBZUAI_ALIGNMENT.md",
    "docs/MILESTONES.md",
    "docs/NEXT_ACTION.md",
    "docs/PROBLEM_DISCOVERY.md",
    "docs/PROBLEM_EVIDENCE_TABLE.csv",
    "docs/PROFILE_GAP_MAP.md",
    "docs/PROJECT_TRACKER.md",
    "docs/RISK_REGISTER.md",
    "docs/SOURCE_REGISTER.md",
    "docs/STATE.md",
    "release/applicant-mastery-signoff.json",
    "reports/media/plategauge-full-page-review.png",
    "reports/release/GATE_D_LOCAL_AUDIT_SUMMARY.md",
    "reports/release/gate-d-local-candidate-audit.json",
}


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
    )


def prospective_source_files(repo_root: str | Path) -> list[Path]:
    """Return the exact tracked-plus-untracked, non-ignored public candidate tree."""

    root = Path(repo_root).resolve()
    top_level = _git(root, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0:
        raise DataIntegrityError(
            "Cannot resolve the Git repository root: "
            + top_level.stderr.decode("utf-8", errors="replace").strip()
        )
    try:
        observed_root = Path(top_level.stdout.rstrip(b"\r\n").decode("utf-8")).resolve()
    except UnicodeDecodeError as exc:
        raise DataIntegrityError("Git repository root is not valid UTF-8") from exc
    if observed_root != root:
        raise DataIntegrityError(
            f"Repository root must be exact; expected {observed_root}, received {root}"
        )

    listed = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if listed.returncode != 0:
        raise DataIntegrityError(
            "Cannot enumerate the prospective public tree: "
            + listed.stderr.decode("utf-8", errors="replace").strip()
        )
    try:
        relative_paths = [
            value.decode("utf-8") for value in listed.stdout.split(b"\0") if value
        ]
    except UnicodeDecodeError as exc:
        raise DataIntegrityError("Prospective public path is not valid UTF-8") from exc
    if len(relative_paths) != len(set(relative_paths)):
        raise DataIntegrityError("Git returned duplicate prospective public paths")

    paths: list[Path] = []
    violations: list[str] = []
    for relative in sorted(relative_paths):
        normalized = Path(relative).as_posix()
        path = root / relative
        if normalized in PRIVATE_OR_LOCAL_FILES or normalized.startswith(PRIVATE_OR_LOCAL_PREFIXES):
            violations.append(normalized)
        if not path.is_file() or path.is_symlink():
            raise DataIntegrityError(
                f"Prospective public entry is absent, non-regular, or a symlink: {normalized}"
            )
        paths.append(path)
    if violations:
        raise DataIntegrityError(
            "Private/generated/cache/checkpoint paths entered the prospective public tree; "
            f"fix .gitignore or the Git index: {violations}"
        )
    return paths


def _relative_set(root: Path, files: Iterable[Path]) -> set[str]:
    return {path.relative_to(root).as_posix() for path in files}


def _task_evidence_files(root: Path) -> set[str]:
    tasks_root = root / "reports/experiments"
    if not tasks_root.is_dir():
        return set()
    evidence: set[str] = set()
    for path in tasks_root.rglob("*"):
        if (
            path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in {".csv", ".json"}
            and "tasks" in path.relative_to(tasks_root).parts
            and ".attempts" not in path.parts
        ):
            evidence.add(path.relative_to(root).as_posix())
    return evidence


def validate_source_inventory(repo_root: str | Path, files: Iterable[Path]) -> dict[str, Any]:
    """Prove that required release and non-checkpoint experiment evidence is included."""

    root = Path(repo_root).resolve()
    candidates = _relative_set(root, files)
    missing_required = sorted(set(REQUIRED_SOURCE_PATHS).difference(candidates))
    if missing_required:
        raise DataIntegrityError(f"Required source evidence is omitted: {missing_required}")
    task_evidence = _task_evidence_files(root)
    missing_task_evidence = sorted(task_evidence.difference(candidates))
    if missing_task_evidence:
        raise DataIntegrityError(
            "Non-checkpoint experiment CSV/JSON evidence is ignored or omitted: "
            f"{missing_task_evidence}"
        )
    workload_evidence = sorted(
        path
        for path in task_evidence
        if "/workload/" in path and Path(path).suffix.lower() in {".csv", ".json"}
    )
    if not workload_evidence:
        raise DataIntegrityError("No non-checkpoint workload CSV/JSON evidence was found")
    return {
        "taskCsvJsonCount": len(task_evidence),
        "taskCsvCount": sum(Path(path).suffix.lower() == ".csv" for path in task_evidence),
        "taskJsonCount": sum(Path(path).suffix.lower() == ".json" for path in task_evidence),
        "workloadCsvJsonCount": len(workload_evidence),
        "workloadCsvCount": sum(
            Path(path).suffix.lower() == ".csv" for path in workload_evidence
        ),
        "workloadJsonCount": sum(
            Path(path).suffix.lower() == ".json" for path in workload_evidence
        ),
    }


def _inventory_digest(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_deterministic_zip(
    target: str | Path,
    root: str | Path,
    files: Iterable[Path],
    *,
    prefix: str = "",
) -> dict[str, Any]:
    """Create a sorted ZIP with normalized timestamps, modes, and entry metadata."""

    destination = Path(target)
    base = Path(root).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(files, key=lambda path: path.relative_to(base).as_posix())
    entries: list[dict[str, Any]] = []
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=True,
        ) as archive:
            archive.comment = b"PlateGauge deterministic Gate D review candidate\n"
            for path in ordered:
                resolved = path.resolve()
                if not resolved.is_relative_to(base) or not resolved.is_file() or path.is_symlink():
                    raise DataIntegrityError(f"Cannot package non-regular source path: {path}")
                relative = resolved.relative_to(base).as_posix()
                archive_name = f"{prefix.rstrip('/')}/{relative}" if prefix else relative
                data = resolved.read_bytes()
                info = zipfile.ZipInfo(archive_name, date_time=ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = ZIP_MODE << 16
                info.flag_bits |= 0x800
                archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
                entries.append(
                    {
                        "path": archive_name,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "filename": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "entryCount": len(entries),
        "inventorySha256": _inventory_digest(entries),
        "deterministicZipMetadata": {
            "entryOrder": "UTF-8 POSIX path ascending",
            "timestamp": "1980-01-01T00:00:00",
            "mode": "100644",
            "compression": "DEFLATE level 9",
        },
        "entries": entries,
    }


def _review_records(output_directory: Path, names: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in sorted(set(names)):
        if Path(name).name != name or name in {".", ".."}:
            raise DataIntegrityError(f"Review deliverable must be a filename, not a path: {name}")
        path = output_directory / name
        if not path.is_file() or path.is_symlink():
            raise DataIntegrityError(f"Required review deliverable is absent or non-regular: {name}")
        records.append(
            {"filename": name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        )
    if not records:
        raise DataIntegrityError("At least one review deliverable is required")
    return records


def create_gate_d_review_package(
    repo_root: str | Path,
    output_directory: str | Path,
    generated_date: str,
    review_deliverables: Iterable[str] = DEFAULT_REVIEW_DELIVERABLES,
) -> dict[str, Any]:
    """Create local draft source/static archives plus their review manifest."""

    root = Path(repo_root).resolve()
    outputs = Path(output_directory).resolve()
    try:
        normalized_date = date.fromisoformat(generated_date).isoformat()
    except ValueError as exc:
        raise DataIntegrityError(f"generated_date must be YYYY-MM-DD: {generated_date}") from exc
    if outputs == root or outputs.is_relative_to(root):
        raise DataIntegrityError("Review outputs must be outside the prospective public repository")
    outputs.mkdir(parents=True, exist_ok=True)

    web_evidence = verify_web_benchmark_evidence(root)
    source_files = prospective_source_files(root)
    source_inventory = validate_source_inventory(root, source_files)
    dist = root / "web/dist"
    static_audit = audit_release_bundle(root, dist)
    static_files = sorted(path for path in dist.rglob("*") if path.is_file() and not path.is_symlink())
    if len(static_files) != int(static_audit["fileCount"]):
        raise DataIntegrityError("Audited static inventory count changed before packaging")

    source_name = f"PlateGauge_Gate_D_Source_and_Evidence_DRAFT_{normalized_date}.zip"
    static_name = f"PlateGauge_Gate_D_Static_Release_Candidate_DRAFT_{normalized_date}.zip"
    source_record = write_deterministic_zip(
        outputs / source_name,
        root,
        source_files,
        prefix="plategauge",
    )
    static_record = write_deterministic_zip(outputs / static_name, dist, static_files)
    review_records = _review_records(outputs, review_deliverables)

    manifest: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "status": "DRAFT_NOT_GATE_D_APPROVED",
        "generatedDate": normalized_date,
        "gateCDecision": "benchmark_failure_explorer",
        "deploymentAuthorized": False,
        "sourceEnumeration": "git ls-files --cached --others --exclude-standard -z",
        "sourceInventory": {
            "prospectivePublicFileCount": len(source_files),
            **source_inventory,
            "webBenchmarkEvidenceSha256": web_evidence["sha256"],
        },
        "staticAudit": {
            "status": static_audit["status"],
            "fileCount": static_audit["fileCount"],
            "inventorySha256": static_audit["inventorySha256"],
        },
        "archives": {
            "sourceAndEvidence": source_record,
            "staticReleaseCandidate": static_record,
        },
        "reviewDeliverables": review_records,
        "exclusions": [
            "Git-ignored raw data, caches, checkpoints, virtual environments, dependencies, and generated build/test output",
            "Private docs/application and docs/mastery drafts from the public source archive; retained only in named private review deliverables where applicable",
            "Internal discovery, selection, detailed governance, contribution/AI, continuity, and review records",
            "Git history and ignored local logs",
        ],
    }
    manifest_path = outputs / "PlateGauge_Gate_D_Package_Manifest.json"
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.", suffix=".tmp", dir=outputs
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(manifest_bytes)
        os.replace(temporary, manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "status": manifest["status"],
        "manifest": manifest_path.name,
        "manifestSha256": sha256_file(manifest_path),
        "source": {
            key: source_record[key] for key in ("filename", "bytes", "sha256", "entryCount")
        },
        "static": {
            key: static_record[key] for key in ("filename", "bytes", "sha256", "entryCount")
        },
        "sourceInventory": manifest["sourceInventory"],
    }


__all__ = [
    "DEFAULT_REVIEW_DELIVERABLES",
    "create_gate_d_review_package",
    "prospective_source_files",
    "validate_source_inventory",
    "write_deterministic_zip",
]
