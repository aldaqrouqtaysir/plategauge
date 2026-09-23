"""Independent, stdlib-only gate for one immutable experimental-camera release.

Inventory creation records bytes, not approval. The approval command only reads
an existing, committed human-authorized approval record. Nothing here creates
approval, modifies Git, follows redirects, or invokes a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

APP_SOURCE_COMMIT = "1f55a7b21cf0aff395df4930d0232a0b0838361d"
ROLLBACK_SOURCE_COMMIT = "b6a3c2519c78d83669444c31c7c139920a1c4506"
RELEASE_TAG = "camera-experimental-r4"
PUBLIC_URL = "https://aldaqrouqtaysir.github.io/plategauge/"
APPROVER = "Taysir Al Daqrouq"
APPROVAL_PATH = "release/camera-r4/approval.json"
INVENTORY_PATH = "release/camera-r4/inventory.json"
ROLLBACK_INVENTORY_PATH = "release/camera-r4/rollback-inventory.json"
EVIDENCE_PATH = "release/camera-r4/verification-evidence.json"
MODEL_SHA256 = "9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675"
MODEL_SIZE = 10_355_122
MAX_JSON_BYTES = 1_048_576
MAX_FILE_BYTES = 134_217_728
MAX_TOTAL_BYTES = 268_435_456
MAX_FILES = 512
CAMERA_FILE_COUNT = 45
ROLLBACK_FILE_COUNT = 36
MAX_ARCHIVE_BYTES = MAX_TOTAL_BYTES + 1_048_576
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
SAFE_PATH = re.compile(r"[A-Za-z0-9._/-]+\Z")
RESERVED = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?\Z", re.I)
REQUIRED_FILES = frozenset(
    {
        "index.html",
        "models/plategauge.onnx",
        "models/release.json",
        "evidence/benchmark-evidence.json",
        "legal/NOTICE.txt",
        "legal/LICENSE.txt",
        "legal/PRIVACY_NOTICE.md",
        "legal/THIRD_PARTY_LICENSES.json",
        "ort/ort-wasm-simd-threaded.mjs",
        "ort/ort-wasm-simd-threaded.wasm",
    }
)
RETIRED_CAMERA_FILES = frozenset({"legal/AI_ASSISTANCE_LOG.md"})
ROLLBACK_REQUIRED_FILES = REQUIRED_FILES | RETIRED_CAMERA_FILES
CAMERA_FILES = frozenset(
    {
        "legal/CAMERA_PRIVACY_NOTICE.md",
        "legal/CAMERA_SYSTEM_CARD.md",
        "legal/PILLOW_RESAMPLING_NOTICE.md",
    }
)
INVENTORY_KEYS = {"schemaVersion", "appSourceCommit", "files"}
APPROVAL_KEYS = {
    "schemaVersion",
    "decision",
    "approvedBy",
    "approvedAt",
    "scope",
    "releaseTag",
    "appSourceCommit",
    "operationsSourceCommit",
    "publicUrl",
    "inventorySha256",
    "bundleArchiveSha256",
    "rollbackArchiveSha256",
    "rollbackInventorySha256",
    "verificationEvidenceSha256",
}
OPERATIONS_FILES = frozenset(
    {
        "README.md",
        "CHANGELOG.md",
        "docs/CURRENT_RELEASE.md",
        "docs/CAMERA_R4_RELEASE.md",
        ".github/workflows/release-camera-r4-pages.yml",
        ".github/workflows/weekly-camera-r4-smoke.yml",
        ".github/workflows/rollback-camera-r4-pages.yml",
        ".github/workflows/weekly-smoke.yml",
        ".github/workflows/release-pages.yml",
    }
)
WORKFLOW_GUARDS = {
    ".github/workflows/weekly-smoke.yml": (
        b"    if: ${{ vars.PLATEGAUGE_ACTIVE_PROFILE != 'camera-experimental-r1' && vars.PLATEGAUGE_ACTIVE_PROFILE != 'camera-experimental-r2' && vars.PLATEGAUGE_ACTIVE_PROFILE != 'camera-experimental-r3' }}\n",
        b"    if: ${{ vars.PLATEGAUGE_ACTIVE_PROFILE != 'camera-experimental-r1' && vars.PLATEGAUGE_ACTIVE_PROFILE != 'camera-experimental-r2' && vars.PLATEGAUGE_ACTIVE_PROFILE != 'camera-experimental-r3' && vars.PLATEGAUGE_ACTIVE_PROFILE != 'camera-experimental-r4' }}\n",
    ),
    ".github/workflows/release-pages.yml": (
        b"    if: ${{ github.event_name != 'release' || (github.event.release.tag_name != 'camera-experimental-r1' && github.event.release.tag_name != 'camera-experimental-r2' && github.event.release.tag_name != 'camera-experimental-r3') }}\n",
        b"    if: ${{ github.event_name != 'release' || (github.event.release.tag_name != 'camera-experimental-r1' && github.event.release.tag_name != 'camera-experimental-r2' && github.event.release.tag_name != 'camera-experimental-r3' && github.event.release.tag_name != 'camera-experimental-r4') }}\n",
    ),
}


class VerificationError(ValueError):
    """A release or observation fails the explicit immutable contract."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise VerificationError(f"Non-finite JSON constant: {value}")


def _no_links(path: Path) -> None:
    absolute = path.absolute()
    for item in (absolute, *absolute.parents):
        if item.is_symlink() or item.is_junction():
            raise VerificationError(f"Symlink/junction is forbidden: {item}")


def _file_bytes(path: Path, maximum: int) -> bytes:
    _no_links(path)
    try:
        initial = path.stat()
        if not stat.S_ISREG(initial.st_mode) or initial.st_size > maximum:
            raise VerificationError(f"Not a bounded regular file: {path}")
        with path.open("rb") as handle:
            value = handle.read(maximum + 1)
        final = path.stat()
        if (initial.st_size, initial.st_mtime_ns, initial.st_ino) != (
            final.st_size,
            final.st_mtime_ns,
            final.st_ino,
        ) or len(value) != initial.st_size:
            raise VerificationError(f"File changed during verification: {path}")
        return value
    except OSError as exc:
        raise VerificationError(f"Cannot read required file: {path}") from exc


def _json_bytes(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_JSON_BYTES:
        raise VerificationError("JSON must be nonempty and bounded")
    try:
        result = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise VerificationError("Malformed UTF-8 JSON") from exc
    if type(result) is not dict:
        raise VerificationError("JSON root must be an object")
    return result


def read_json(path: Path) -> dict[str, Any]:
    return _json_bytes(_file_bytes(path, MAX_JSON_BYTES))


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise VerificationError(f"{label} must be lowercase SHA-256")
    return value


def _relative(value: object) -> str:
    if not isinstance(value, str) or len(value) > 240 or not SAFE_PATH.fullmatch(value):
        raise VerificationError("Invalid relative inventory path")
    parts = value.split("/")
    if any(
        part in {"", ".", ".."} or part.endswith(".") or RESERVED.fullmatch(part) for part in parts
    ):
        raise VerificationError("Unsafe relative inventory path")
    if any(part.startswith(".") for part in parts) and value != ".nojekyll":
        raise VerificationError("Hidden inventory paths are forbidden")
    return value


def validate_inventory(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if (
        set(payload) != INVENTORY_KEYS
        or type(payload["schemaVersion"]) is not int
        or payload["schemaVersion"] != 1
        or payload["appSourceCommit"] not in (APP_SOURCE_COMMIT, ROLLBACK_SOURCE_COMMIT)
    ):
        raise VerificationError("Inventory schema/app identity differs from camera release")
    entries = payload["files"]
    if type(entries) is not list or not 1 <= len(entries) <= MAX_FILES:
        raise VerificationError("Inventory must contain a bounded nonempty file list")
    names: list[str] = []
    total = 0
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"path", "size", "sha256"}:
            raise VerificationError("Inventory file fields differ from schema")
        name = _relative(entry["path"])
        size = entry["size"]
        if (
            type(size) is not int
            or not 0 <= size <= MAX_FILE_BYTES
            or (size == 0 and name != ".nojekyll")
        ):
            raise VerificationError(
                "Inventory file size must be a bounded integer; content required"
            )
        _digest(entry["sha256"], "File hash")
        names.append(name)
        total += size
    if names != sorted(names) or len({name.casefold() for name in names}) != len(names):
        raise VerificationError("Inventory paths must be sorted, unique and case-distinct")
    if total > MAX_TOTAL_BYTES:
        raise VerificationError("Inventory total exceeds bundle limit")
    camera = payload["appSourceCommit"] == APP_SOURCE_COMMIT
    expected_count = CAMERA_FILE_COUNT if camera else ROLLBACK_FILE_COUNT
    if len(entries) != expected_count:
        raise VerificationError("Inventory file count differs from the exact release profile")
    if camera and any(name.casefold() in {item.casefold() for item in RETIRED_CAMERA_FILES}
                      for name in names):
        raise VerificationError("Camera inventory contains a retired presentation resource")
    required = REQUIRED_FILES | CAMERA_FILES if camera else ROLLBACK_REQUIRED_FILES
    if (
        not required.issubset(names)
        or not any(name.startswith("assets/") and name.endswith(".js") for name in names)
        or not any(name.startswith("assets/") and name.endswith(".css") for name in names)
    ):
        raise VerificationError("Inventory is missing required camera resources")
    model = next(item for item in entries if item["path"] == "models/plategauge.onnx")
    if model["sha256"] != MODEL_SHA256 or model["size"] != MODEL_SIZE:
        raise VerificationError("Inventory must bind the unchanged pinned baseline model")
    return list(entries)


def inventory_bundle(bundle: Path, app_source_commit: str = APP_SOURCE_COMMIT) -> dict[str, Any]:
    _no_links(bundle)
    if not bundle.is_dir():
        raise VerificationError("Bundle must be a regular directory")
    files: list[dict[str, Any]] = []
    for directory, subdirs, names in os.walk(bundle, followlinks=False):
        for name in subdirs:
            path = Path(directory) / name
            _no_links(path)
            if not stat.S_ISDIR(path.stat().st_mode):
                raise VerificationError("Bundle contains a non-directory")
        for name in names:
            path = Path(directory) / name
            relative = _relative(path.relative_to(bundle).as_posix())
            raw = _file_bytes(path, MAX_FILE_BYTES)
            files.append(
                {"path": relative, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            )
            if len(files) > MAX_FILES or sum(item["size"] for item in files) > MAX_TOTAL_BYTES:
                raise VerificationError("Bundle exceeds size/count limits")
    files.sort(key=lambda item: item["path"])
    payload = {"schemaVersion": 1, "appSourceCommit": app_source_commit, "files": files}
    validate_inventory(payload)
    return payload


def create_inventory(
    bundle: Path, output: Path, app_source_commit: str = APP_SOURCE_COMMIT
) -> dict[str, Any]:
    _no_links(output)
    if output.absolute().is_relative_to(bundle.absolute()):
        raise VerificationError("Inventory output must be outside its bundle")
    payload = inventory_bundle(bundle, app_source_commit)
    raw = (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    try:
        with output.open("xb") as handle:
            handle.write(raw)
    except OSError as exc:
        raise VerificationError(
            "Inventory output must be a fresh file in an existing directory"
        ) from exc
    return {
        "status": "inventoried-not-approved",
        "fileCount": len(payload["files"]),
        "inventorySha256": hashlib.sha256(raw).hexdigest(),
    }


def verify_bundle(inventory: Path, bundle: Path) -> dict[str, Any]:
    raw = _file_bytes(inventory, MAX_JSON_BYTES)
    expected = _json_bytes(raw)
    validate_inventory(expected)
    actual = inventory_bundle(bundle, expected["appSourceCommit"])
    if expected != actual:
        raise VerificationError(
            "Bundle differs from approved inventory (missing/extra/changed file)"
        )
    return {
        "status": "verified",
        "fileCount": len(expected["files"]),
        "inventorySha256": hashlib.sha256(raw).hexdigest(),
    }


def _archive_hash(archive: Path) -> str:
    _no_links(archive)
    info = archive.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ARCHIVE_BYTES:
        raise VerificationError("Archive must be a bounded nonempty regular file")
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    final = archive.stat()
    if (info.st_size, info.st_mtime_ns, info.st_ino) != (
        final.st_size,
        final.st_mtime_ns,
        final.st_ino,
    ):
        raise VerificationError("Archive changed during hashing")
    return digest.hexdigest()


def pack_bundle(inventory: Path, bundle: Path, output: Path) -> dict[str, Any]:
    result = verify_bundle(inventory, bundle)
    _no_links(output)
    if output.absolute().is_relative_to(bundle.absolute()):
        raise VerificationError("Archive output must be outside its bundle")
    entries = validate_inventory(read_json(inventory))
    try:
        with (
            output.open("xb") as handle,
            zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_STORED) as archive,
        ):
            for entry in entries:
                raw = _file_bytes(bundle / entry["path"], MAX_FILE_BYTES)
                if len(raw) != entry["size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                    raise VerificationError("Bundle changed while packing")
                info = zipfile.ZipInfo(entry["path"], date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, raw)
    except (OSError, zipfile.BadZipFile) as exc:
        raise VerificationError("Cannot create new deterministic archive") from exc
    return {**result, "archiveSha256": _archive_hash(output)}


def _archive_entries(archive: zipfile.ZipFile, entries: list[dict[str, Any]]) -> None:
    infos = archive.infolist()
    if archive.comment or len(infos) != len(entries):
        raise VerificationError("Archive entry count/comment differs from contract")
    if [item.filename for item in infos] != [item["path"] for item in entries]:
        raise VerificationError("Archive members must exactly match sorted inventory")
    for info, entry in zip(infos, entries, strict=True):
        _relative(info.filename)
        if (
            info.is_dir()
            or info.create_system != 3
            or info.external_attr >> 16 != stat.S_IFREG | 0o644
            or info.extra
            or info.comment
            or info.flag_bits & ~0x800
            or info.compress_type != zipfile.ZIP_STORED
            or info.file_size != entry["size"]
            or info.compress_size != entry["size"]
        ):
            raise VerificationError(
                "Archive contains non-regular, compressed or unexpected entry metadata"
            )
        digest = hashlib.sha256()
        count = 0
        with archive.open(info, "r") as handle:
            for chunk in iter(lambda: handle.read(65_536), b""):
                count += len(chunk)
                if count > entry["size"]:
                    raise VerificationError("Archive entry exceeds approved size")
                digest.update(chunk)
        if count != entry["size"] or digest.hexdigest() != entry["sha256"]:
            raise VerificationError("Archive content differs from inventory")


def _bounded_zip_directory(path: Path) -> None:
    """Bound central-directory parsing before ZipFile can allocate its entry list."""
    size = path.stat().st_size
    if size < 22:
        raise VerificationError("Archive lacks its bounded ZIP directory")
    with path.open("rb") as handle:
        handle.seek(-22, os.SEEK_END)
        signature, disk, start_disk, disk_entries, entries, directory_size, offset, comment = (
            struct.unpack("<4s4H2IH", handle.read(22))
        )
    if (
        signature != b"PK\x05\x06"
        or disk != 0
        or start_disk != 0
        or comment != 0
        or disk_entries != entries
        or not 1 <= entries <= MAX_FILES
        or directory_size > MAX_FILES * (46 + 240)
        or offset + directory_size + 22 != size
    ):
        raise VerificationError(
            "Only bounded single-disk non-ZIP64 archives without trailers are accepted"
        )


def extract_bundle(
    inventory: Path, archive_path: Path, expected_sha256: str, destination: Path
) -> dict[str, Any]:
    expected = _digest(expected_sha256, "Expected archive hash")
    entries = validate_inventory(read_json(inventory))
    _no_links(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise VerificationError("Extraction requires a new destination in an existing directory")
    if _archive_hash(archive_path) != expected:
        raise VerificationError("Archive hash differs from approved archive")
    _bounded_zip_directory(archive_path)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            # All metadata, CRCs and content hashes are verified BEFORE creating destination.
            _archive_entries(archive, entries)
            destination.mkdir()
            for entry in entries:
                target = destination / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                _no_links(target)
                with archive.open(entry["path"], "r") as source, target.open("xb") as output:
                    count = 0
                    while chunk := source.read(65_536):
                        count += len(chunk)
                        if count > entry["size"]:
                            raise VerificationError("Archive changed while extracting")
                        output.write(chunk)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise VerificationError(
            "Archive extraction failed; do not use any partial destination"
        ) from exc
    if _archive_hash(archive_path) != expected:
        raise VerificationError("Archive changed during extraction")
    result = verify_bundle(inventory, destination)
    return {**result, "archiveSha256": expected}


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationError("Required read-only Git identity check failed") from exc
    return result.stdout


def _changed_paths(root: Path, before: str, after: str) -> set[str]:
    raw = _git(root, "diff", "--no-ext-diff", "--name-only", "--no-renames", "-z", before, after)
    return {part.decode("utf-8") for part in raw.split(b"\0") if part}


def _timestamp(value: object) -> None:
    if not isinstance(value, str) or len(value) > 40:
        raise VerificationError("Approval timestamp must be aware ISO-8601")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationError("Approval timestamp must be aware ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise VerificationError("Approval timestamp must have a UTC offset")


def verify_approval(
    root: Path, approval: Path, expected_tag: str, *, require_tag: bool = False
) -> dict[str, Any]:
    """Validate an existing approval-only commit; never grant authority itself."""
    _no_links(root)
    if expected_tag != RELEASE_TAG:
        raise VerificationError("Only the exact experimental-camera tag is supported")
    expected_path = root / APPROVAL_PATH
    supplied = approval if approval.is_absolute() else root / approval
    if supplied.absolute() != expected_path.absolute():
        raise VerificationError("Approval path must be the canonical camera approval path")
    raw = _file_bytes(expected_path, MAX_JSON_BYTES)
    payload = _json_bytes(raw)
    if (
        set(payload) != APPROVAL_KEYS
        or type(payload["schemaVersion"]) is not int
        or payload["schemaVersion"] != 1
    ):
        raise VerificationError("Approval fields differ from strict camera schema")
    fixed = {
        "decision": "approved",
        "approvedBy": APPROVER,
        "scope": "experimental-camera-publication",
        "releaseTag": RELEASE_TAG,
        "appSourceCommit": APP_SOURCE_COMMIT,
        "publicUrl": PUBLIC_URL,
    }
    if any(payload[key] != value for key, value in fixed.items()):
        raise VerificationError("Approval scope, decision or identity differs from camera contract")
    _timestamp(payload["approvedAt"])
    operations = payload["operationsSourceCommit"]
    if not isinstance(operations, str) or not COMMIT.fullmatch(operations):
        raise VerificationError("Operations source must be a full lowercase commit SHA")
    inventory_raw = _file_bytes(root / INVENTORY_PATH, MAX_JSON_BYTES)
    camera_inventory = _json_bytes(inventory_raw)
    validate_inventory(camera_inventory)
    if camera_inventory["appSourceCommit"] != APP_SOURCE_COMMIT:
        raise VerificationError("Camera inventory must identify the frozen camera source")
    if (
        _digest(payload["inventorySha256"], "Approved inventory")
        != hashlib.sha256(inventory_raw).hexdigest()
    ):
        raise VerificationError("Approval does not bind the committed inventory bytes")
    for key, path, source in (
        ("rollbackInventorySha256", ROLLBACK_INVENTORY_PATH, ROLLBACK_SOURCE_COMMIT),
        ("verificationEvidenceSha256", EVIDENCE_PATH, None),
    ):
        bound_raw = _file_bytes(root / path, MAX_JSON_BYTES)
        bound_payload = _json_bytes(bound_raw)
        if source is not None:
            validate_inventory(bound_payload)
            if bound_payload["appSourceCommit"] != source:
                raise VerificationError("Rollback inventory source identity mismatch")
        elif not bound_payload:
            raise VerificationError("Verification evidence must not be empty")
        if _digest(payload[key], key) != hashlib.sha256(bound_raw).hexdigest():
            raise VerificationError(f"Approval hash differs for {path}")
        if _git(root, "show", f"HEAD:{path}") != bound_raw:
            raise VerificationError(f"Committed bytes differ for {path}")
    for key in ("bundleArchiveSha256", "rollbackArchiveSha256"):
        _digest(payload[key], key)
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise VerificationError("Release checkout must be clean")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    if (
        require_tag
        and _git(root, "rev-parse", "--verify", f"refs/tags/{RELEASE_TAG}^{{commit}}")
        .decode()
        .strip()
        != head
    ):
        raise VerificationError(
            "Immutable experimental-camera tag must resolve to this approval HEAD"
        )
    parents = _git(root, "rev-list", "--parents", "-n", "1", "HEAD").decode().split()
    if parents != [head, operations]:
        raise VerificationError("Approval commit must have exactly the reviewed operations parent")
    if _changed_paths(root, operations, head) != {APPROVAL_PATH}:
        raise VerificationError("Approval-only child may change only its new approval record")
    if _git(root, "ls-tree", operations, "--", APPROVAL_PATH).strip():
        raise VerificationError("An approval must not rewrite an existing approval record")
    if _git(root, "show", f"HEAD:{APPROVAL_PATH}") != raw:
        raise VerificationError("Approval checkout bytes differ from committed approval")
    if _git(root, "show", f"HEAD:{INVENTORY_PATH}") != inventory_raw:
        raise VerificationError("Inventory checkout bytes differ from committed inventory")
    _git(root, "merge-base", "--is-ancestor", APP_SOURCE_COMMIT, operations)
    changed = _changed_paths(root, APP_SOURCE_COMMIT, operations)
    if any(
        path not in OPERATIONS_FILES and not path.startswith("release/camera-r4/") for path in changed
    ):
        raise VerificationError("Operations source changes a protected app/scientific path")
    if APPROVAL_PATH in changed:
        raise VerificationError("Operations source must not already contain camera approval")
    # Endpoint equality alone must not hide protected changes later reverted, or
    # a merged private lineage. Every new operation commit is linear and bounded.
    for row in (
        _git(root, "rev-list", "--parents", f"{APP_SOURCE_COMMIT}..{operations}")
        .decode()
        .splitlines()
    ):
        commits = row.split()
        if len(commits) != 2:
            raise VerificationError("Release operations must have a linear public-source lineage")
        for path in _changed_paths(root, commits[1], commits[0]):
            if path not in OPERATIONS_FILES and not path.startswith("release/camera-r4/"):
                raise VerificationError("An operations-history commit changes a protected path")
            if path == APPROVAL_PATH:
                raise VerificationError("Operations history may not contain prior camera approval")
    for path, (previous_guard, next_guard) in WORKFLOW_GUARDS.items():
        if path in changed:
            original = _git(root, "show", f"{APP_SOURCE_COMMIT}:{path}")
            current = _git(root, "show", f"{operations}:{path}")
            if original.count(previous_guard) != 1 or current != original.replace(
                previous_guard, next_guard, 1
            ):
                raise VerificationError(
                    "Historical workflow may only replace its r1+r2+r3 guard with the exact r1+r2+r3+r4 guard"
                )
    for record in _git(root, "ls-tree", "-r", "-z", head).split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        if name.decode("utf-8") in changed | {APPROVAL_PATH} and not metadata.startswith(
            b"100644 blob "
        ):
            raise VerificationError(
                "Release operations must contain only regular non-executable files"
            )
    return {
        "status": "verified",
        "releaseTag": RELEASE_TAG,
        "appSourceCommit": APP_SOURCE_COMMIT,
        "operationsSourceCommit": operations,
        "approvalCommit": head,
        "inventorySha256": payload["inventorySha256"],
        "publicUrl": PUBLIC_URL,
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise VerificationError("Redirects are forbidden during deployed-byte verification")


def verify_live(inventory: Path, url: str) -> dict[str, Any]:
    if url != PUBLIC_URL:
        raise VerificationError("Live destination must equal the approved HTTPS Pages URL")
    raw = _file_bytes(inventory, MAX_JSON_BYTES)
    entries = validate_inventory(_json_bytes(raw))
    opener = urllib.request.build_opener(_NoRedirect())
    deadline = time.monotonic() + 300
    for entry in entries:
        target = url + ("" if entry["path"] == "index.html" else entry["path"])
        request = urllib.request.Request(target, headers={"Accept-Encoding": "identity"})
        digest = hashlib.sha256()
        total = 0
        try:
            with opener.open(request, timeout=20) as response:
                if response.status != 200 or response.geturl() != target:
                    raise VerificationError("Live response changed URL or did not return 200")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise VerificationError("Encoded live responses are not accepted")
                length = response.headers.get("Content-Length")
                if length is not None and (
                    not length.isascii() or not length.isdigit() or int(length) != entry["size"]
                ):
                    raise VerificationError("Live Content-Length differs from approved bytes")
                while True:
                    if time.monotonic() > deadline:
                        raise VerificationError("Live verification exceeded total time budget")
                    chunk = response.read(min(65_536, entry["size"] - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > entry["size"]:
                        raise VerificationError("Live file exceeds approved size")
                    digest.update(chunk)
        except (OSError, urllib.error.URLError) as exc:
            raise VerificationError(f"Live request failed for {entry['path']}") from exc
        if total != entry["size"] or digest.hexdigest() != entry["sha256"]:
            raise VerificationError(f"Live bytes differ for {entry['path']}")
    return {
        "status": "verified",
        "publicUrl": url,
        "fileCount": len(entries),
        "inventorySha256": hashlib.sha256(raw).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("inventory")
    create.add_argument("--bundle", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument(
        "--app-source-commit",
        choices=[APP_SOURCE_COMMIT, ROLLBACK_SOURCE_COMMIT],
        default=APP_SOURCE_COMMIT,
    )
    bundle = commands.add_parser("bundle")
    bundle.add_argument("--bundle", type=Path, required=True)
    bundle.add_argument("--inventory", type=Path, required=True)
    pack = commands.add_parser("pack")
    pack.add_argument("--inventory", type=Path, required=True)
    pack.add_argument("--bundle", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    extract = commands.add_parser("extract")
    extract.add_argument("--inventory", type=Path, required=True)
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--expected-sha256", required=True)
    extract.add_argument("--destination", type=Path, required=True)
    approval = commands.add_parser("approval")
    approval.add_argument("--repo-root", type=Path, required=True)
    approval.add_argument("--approval", type=Path, default=Path(APPROVAL_PATH))
    approval.add_argument("--expected-tag", required=True)
    approval.add_argument("--require-tag", action="store_true")
    live = commands.add_parser("live")
    live.add_argument("--inventory", type=Path, required=True)
    live.add_argument("--url", required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "inventory":
            result = create_inventory(
                arguments.bundle, arguments.output, arguments.app_source_commit
            )
        elif arguments.command == "bundle":
            result = verify_bundle(arguments.inventory, arguments.bundle)
        elif arguments.command == "approval":
            result = verify_approval(
                arguments.repo_root,
                arguments.approval,
                arguments.expected_tag,
                require_tag=arguments.require_tag,
            )
        elif arguments.command == "pack":
            result = pack_bundle(arguments.inventory, arguments.bundle, arguments.output)
        elif arguments.command == "extract":
            result = extract_bundle(
                arguments.inventory,
                arguments.archive,
                arguments.expected_sha256,
                arguments.destination,
            )
        else:
            result = verify_live(arguments.inventory, arguments.url)
    except (VerificationError, OSError, UnicodeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
