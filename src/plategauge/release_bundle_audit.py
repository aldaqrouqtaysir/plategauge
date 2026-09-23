"""Fail-closed audit for the exact static PlateGauge release bundle."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .data import sha256_file
from .errors import DataIntegrityError
from .web_evidence import verify_web_benchmark_evidence

SCHEMA_VERSION = 1
MODEL_SHA256 = "9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675"
EXAMPLE_IDS = (
    "lefood-0142",
    "lefood-0192",
    "lefood-0226",
    "lefood-0320",
    "lefood-0400",
    "lefood-0441",
    "lefood-0461",
    "lefood-0489",
    "lefood-0507",
    "lefood-0530",
)
ASSET_PATTERNS = (
    re.compile(r"assets/index-[A-Za-z0-9_-]+\.js"),
    re.compile(r"assets/index-[A-Za-z0-9_-]+\.css"),
    re.compile(r"assets/model\.worker-[A-Za-z0-9_-]+\.js"),
)
FORBIDDEN_SUFFIXES = {
    ".7z",
    ".csv",
    ".gz",
    ".map",
    ".rar",
    ".tar",
    ".tgz",
    ".xls",
    ".xlsx",
    ".zip",
}
LOCAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/]Users[\\/]", re.IGNORECASE),
    re.compile("/" + r"Users/[^/\s]+/", re.IGNORECASE),
    # ONNX Runtime intentionally embeds the virtual WASI value
    # ``/home/web_user``; it is not a build-host path.
    re.compile("/" + r"home/(?!web_user(?:/|\b))[^/\s]+/", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)
FORBIDDEN_PUBLIC_STATUS_PHRASES = (
    "not released",
    "pending gate d",
    "planned for github pages",
    "no public url",
)


class _ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.resources: list[str] = []
        self.csp: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if tag in {"script", "img", "source"} and values.get("src"):
            self.resources.append(str(values["src"]))
        if tag == "link" and values.get("href"):
            self.resources.append(str(values["href"]))
        if (
            tag == "meta"
            and str(values.get("http-equiv", "")).lower() == "content-security-policy"
        ):
            self.csp = values.get("content")


def _strict_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataIntegrityError(f"Cannot read strict JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataIntegrityError(f"JSON root must be an object: {path}")
    return payload


def _bundle_inventory(directory: Path) -> dict[str, Path]:
    if not directory.is_dir() or directory.is_symlink():
        raise DataIntegrityError(f"Release bundle must be a regular directory: {directory}")
    inventory: dict[str, Path] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise DataIntegrityError(f"Release bundle contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        inventory[relative] = path
    return inventory


def _expected_static_files() -> set[str]:
    files = {
        "index.html",
        "evidence/benchmark-evidence.json",
        "examples/ATTRIBUTION.md",
        "legal/LICENSE.txt",
        "legal/NOTICE.txt",
        "legal/PRIVACY_NOTICE.md",
        "legal/THIRD_PARTY_LICENSES.json",
        "models/README.md",
        "models/plategauge.onnx",
        "models/release.json",
        "ort/ort-wasm-simd-threaded.mjs",
        "ort/ort-wasm-simd-threaded.wasm",
    }
    for sample_id in EXAMPLE_IDS:
        files.add(f"examples/{sample_id}-before.jpg")
        files.add(f"examples/{sample_id}-after.jpg")
    return files


def _validate_inventory(inventory: dict[str, Path]) -> list[str]:
    forbidden = sorted(
        relative for relative in inventory if Path(relative).suffix.lower() in FORBIDDEN_SUFFIXES
    )
    if forbidden:
        raise DataIntegrityError(f"Release bundle contains forbidden files: {forbidden}")
    expected = _expected_static_files()
    dynamic: list[str] = []
    for pattern in ASSET_PATTERNS:
        matches = sorted(relative for relative in inventory if pattern.fullmatch(relative))
        if len(matches) != 1:
            raise DataIntegrityError(
                f"Release bundle must contain one asset matching {pattern.pattern}: {matches}"
            )
        dynamic.extend(matches)
    actual = set(inventory)
    allowed = expected.union(dynamic)
    missing = sorted(allowed.difference(actual))
    unexpected = sorted(actual.difference(allowed))
    if missing or unexpected:
        raise DataIntegrityError(
            f"Release bundle allowlist mismatch; missing={missing}, unexpected={unexpected}"
        )
    return sorted(dynamic)


def _validate_text_hygiene(inventory: dict[str, Path]) -> None:
    text_suffixes = {".css", ".html", ".js", ".json", ".md", ".mjs", ".txt"}
    for relative, path in inventory.items():
        if path.suffix.lower() not in text_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise DataIntegrityError(f"Cannot inspect release text {relative}: {exc}") from exc
        if any(pattern.search(text) for pattern in LOCAL_PATH_PATTERNS):
            raise DataIntegrityError(f"Release text contains a host-specific path: {relative}")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise DataIntegrityError(f"Release text contains a high-confidence secret: {relative}")
        lowered = text.lower()
        stale_status = [
            phrase for phrase in FORBIDDEN_PUBLIC_STATUS_PHRASES if phrase in lowered
        ]
        if stale_status:
            raise DataIntegrityError(
                f"Release text contains stale pre-release status language: "
                f"{relative}: {stale_status}"
            )


def _validate_html(index_path: Path) -> list[str]:
    parser = _ResourceParser()
    parser.feed(index_path.read_text(encoding="utf-8"))
    remote = sorted(
        resource
        for resource in parser.resources
        if resource.startswith(("http://", "https://", "//"))
    )
    if remote:
        raise DataIntegrityError(f"Release HTML loads third-party resources: {remote}")
    required_csp = ("default-src 'self'", "connect-src 'self'", "object-src 'none'")
    if parser.csp is None or any(fragment not in parser.csp for fragment in required_csp):
        raise DataIntegrityError("Release HTML lacks the required restrictive CSP")
    if "frame-ancestors" in parser.csp:
        raise DataIntegrityError(
            "Meta-delivered CSP must not claim frame-ancestors protection; use a verified "
            "HTTP response header on a host that supports it"
        )
    return parser.resources


def _validate_examples(repo_root: Path, inventory: dict[str, Path]) -> dict[str, str]:
    manifest_path = repo_root / "data/manifests/lefood_v1_manifest.csv"
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = {row["sample_id"]: row for row in csv.DictReader(handle)}
    hashes: dict[str, str] = {}
    for sample_id in EXAMPLE_IDS:
        if sample_id not in rows:
            raise DataIntegrityError(f"Example ID is absent from the frozen manifest: {sample_id}")
        row = rows[sample_id]
        for role in ("before", "after"):
            relative = f"examples/{sample_id}-{role}.jpg"
            actual = sha256_file(inventory[relative])
            expected = row[f"{role}_sha256"]
            if actual != expected:
                raise DataIntegrityError(f"Example bytes differ from the frozen manifest: {relative}")
            hashes[relative] = actual
    return hashes


def _validate_notices(repo_root: Path, inventory: dict[str, Path]) -> dict[str, str]:
    source_map = {
        "legal/LICENSE.txt": repo_root / "LICENSE",
        "legal/NOTICE.txt": repo_root / "NOTICE",
        "legal/PRIVACY_NOTICE.md": repo_root / "docs/PRIVACY_NOTICE.md",
        "legal/THIRD_PARTY_LICENSES.json": (
            repo_root / "reports/security/node-production-licenses.json"
        ),
    }
    hashes: dict[str, str] = {}
    for relative, source in source_map.items():
        if inventory[relative].read_bytes() != source.read_bytes():
            raise DataIntegrityError(f"Bundled legal evidence differs from source: {relative}")
        hashes[relative] = sha256_file(inventory[relative])
    notice = inventory["legal/NOTICE.txt"].read_text(encoding="utf-8")
    required = (
        "LeFood-Set v1",
        "CC BY 4.0",
        "10.17632/cchsk79jkt.1",
        "1824797e7887cbec1990e4adbd6675960a36c589",
        "46d2c063b18125884c48937afa4c49e18128869e52e8db96df48bf0a4d7ff697",
        MODEL_SHA256,
        "full dataset archive and source collection are not distributed",
        "20 byte-identical source JPEGs",
    )
    missing = [value for value in required if value not in notice]
    if missing:
        raise DataIntegrityError(f"Bundled notice lacks required attribution: {missing}")
    licenses = _strict_json(inventory["legal/THIRD_PARTY_LICENSES.json"])
    if set(licenses) != {"Apache-2.0", "BSD-3-Clause", "ISC", "MIT"}:
        raise DataIntegrityError("Bundled production dependency licenses are incomplete")
    return hashes


def _validate_benchmark_evidence(
    repo_root: Path,
    inventory: dict[str, Path],
) -> dict[str, Any]:
    verification = verify_web_benchmark_evidence(repo_root)
    relative = "evidence/benchmark-evidence.json"
    bundled = inventory[relative]
    generated = repo_root / "web/src/generated/benchmarkEvidence.json"
    public = repo_root / "web/public/evidence/benchmark-evidence.json"
    if len({path.read_bytes() for path in (bundled, generated, public)}) != 1:
        raise DataIntegrityError(
            "Bundled, generated, and downloadable benchmark evidence bytes differ"
        )
    payload = _strict_json(bundled)
    workload_evidence = payload.get("workloadEvidence")
    category_comparisons = payload.get("categoryComparisons")
    robustness = payload.get("robustnessSummary")
    provenance = payload.get("provenance")
    if (
        payload.get("schemaVersion") != 1
        or not isinstance(workload_evidence, dict)
        or workload_evidence.get("modelAndControlWorkloadCount") != 7
        or workload_evidence.get("contextualReferenceCount") != 1
        or not isinstance(workload_evidence.get("records"), list)
        or len(workload_evidence["records"]) != 8
        or not isinstance(category_comparisons, list)
        or len(category_comparisons) != 34
        or not isinstance(robustness, dict)
        or robustness.get("downgradeRequired") is not True
        or not isinstance(provenance, dict)
        or "reports/robustness.json" not in provenance.get("sourceFiles", {})
    ):
        raise DataIntegrityError("Bundled benchmark evidence violates the public evidence contract")
    return {
        "path": relative,
        "sha256": sha256_file(bundled),
        "sourceFileCount": verification["sourceFileCount"],
        "workloadRecordCount": len(workload_evidence["records"]),
        "categoryRecordCount": len(category_comparisons),
    }


def audit_release_bundle(
    repo_root: str | Path,
    bundle_directory: str | Path,
) -> dict[str, Any]:
    """Validate a production dist directory against the release allowlist."""

    root = Path(repo_root).resolve()
    bundle = Path(bundle_directory)
    if not bundle.is_absolute():
        bundle = root / bundle
    inventory = _bundle_inventory(bundle)
    dynamic_assets = _validate_inventory(inventory)
    _validate_text_hygiene(inventory)
    resources = _validate_html(inventory["index.html"])

    canonical_model = root / "artifacts/plategauge.onnx"
    staged_model = root / "web/public/models/plategauge.onnx"
    bundled_model = inventory["models/plategauge.onnx"]
    hashes = {sha256_file(path) for path in (canonical_model, staged_model, bundled_model)}
    if hashes != {MODEL_SHA256}:
        raise DataIntegrityError("Canonical, staged, and bundled ONNX bytes differ")
    public_manifest = root / "web/public/models/release.json"
    bundled_manifest = inventory["models/release.json"]
    if bundled_manifest.read_bytes() != public_manifest.read_bytes():
        raise DataIntegrityError("Bundled release manifest differs from staged metadata")
    manifest = _strict_json(bundled_manifest)
    if (
        manifest.get("modelSha256") != MODEL_SHA256
        or manifest.get("modelPath") != "models/plategauge.onnx"
        or manifest.get("calibration", {}).get("intervalGatePassed") is not False
    ):
        raise DataIntegrityError("Bundled release manifest violates the frozen release contract")

    example_hashes = _validate_examples(root, inventory)
    notice_hashes = _validate_notices(root, inventory)
    benchmark_evidence = _validate_benchmark_evidence(root, inventory)
    file_hashes = {relative: sha256_file(path) for relative, path in sorted(inventory.items())}
    inventory_digest = hashlib.sha256(
        json.dumps(file_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "passed",
        "kind": "static_release_bundle_audit",
        "bundleDirectory": bundle.relative_to(root).as_posix(),
        "fileCount": len(inventory),
        "inventorySha256": inventory_digest,
        "dynamicAssets": dynamic_assets,
        "htmlResourceReferences": resources,
        "model": {
            "sha256": MODEL_SHA256,
            "sizeBytes": bundled_model.stat().st_size,
            "manifestSha256": sha256_file(bundled_manifest),
            "modelVersion": manifest.get("modelVersion"),
        },
        "examples": {"count": len(example_hashes), "sha256": example_hashes},
        "benchmarkEvidence": benchmark_evidence,
        "legalEvidenceSha256": notice_hashes,
        "sourceMaps": 0,
        "forbiddenFiles": [],
        "remoteRuntimeResources": [],
        "hostPaths": [],
        "highConfidenceSecrets": [],
    }


__all__ = ["audit_release_bundle"]
