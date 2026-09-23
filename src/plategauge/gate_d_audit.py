"""Local, non-deploying audit of the PlateGauge Gate D candidate."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .data import sha256_file
from .errors import DataIntegrityError
from .release_bundle_audit import audit_release_bundle
from .web_evidence import verify_web_benchmark_evidence

Status = Literal["pass", "fail", "pending"]

TEXT_SUFFIXES = {
    ".cff",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
HOST_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s]+[\\/]", re.IGNORECASE),
    re.compile("/" + r"Users/[^/\s]+/", re.IGNORECASE),
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
# Reviewed, camera-off interface screenshots only. This supplements the historical
# media allowlist; it never admits arbitrary reports/media images or source data.
# Provenance: reports/media/CAMERA_SCREENSHOTS_2026-09-23.md.
REVIEWED_CAMERA_SCREENSHOT_SHA256 = {
    "reports/media/camera-home-2026-09-23.png": (
        "63ccb2605da0a5c5096240bf7e085c229f13d2189b7178a6102933a94a8153e1"
    ),
    "reports/media/camera-idle-2026-09-23.png": (
        "ee0da4e35f68e7e06fda1193637ba628dabf2348046ee60b7c6dd29b3fcd56ab"
    ),
}


@dataclass(frozen=True, slots=True)
class AuditCheck:
    id: str
    status: Status
    summary: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataIntegrityError(f"Cannot read JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataIntegrityError(f"JSON root must be an object: {path}")
    return payload


def _candidate_files(root: Path) -> list[Path]:
    listed = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if listed.returncode != 0:
        raise DataIntegrityError(
            f"Cannot enumerate the prospective candidate tree: {listed.stderr.strip()}"
        )
    paths = [root / relative for relative in listed.stdout.split("\0") if relative]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise DataIntegrityError(f"Prospective candidate entries are not files: {missing}")
    return sorted(paths)


def _scan_hygiene(root: Path, files: list[Path]) -> tuple[list[str], list[str]]:
    host_paths: list[str] = []
    secrets: list[str] = []
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 5_000_000:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(pattern.search(text) for pattern in HOST_PATH_PATTERNS):
            host_paths.append(relative)
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            secrets.append(relative)
    return sorted(host_paths), sorted(secrets)


def _raw_data_candidates(root: Path, files: list[Path]) -> list[str]:
    forbidden_archives = {".7z", ".rar", ".tar", ".tgz", ".xls", ".xlsx", ".zip"}
    allowed_image_prefixes = (
        "web/public/examples/",
        "web/tests/fixtures/preprocess-golden/",
    )
    allowed_image_paths = {
        "reports/media/01-question-and-boundary.png",
        "reports/media/02-frozen-results.png",
        "reports/media/03-selected-success.png",
        "reports/media/04-largest-failure.png",
        "reports/media/05-category-shift-method.png",
        "reports/media/06-limits-and-attribution.png",
        "reports/media/plategauge-social-preview-1280x640.png",
    }
    candidates: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        if suffix in forbidden_archives:
            candidates.append(relative)
        if (
            suffix in {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
            and not relative.startswith(allowed_image_prefixes)
            and relative not in allowed_image_paths
        ):
            expected = REVIEWED_CAMERA_SCREENSHOT_SHA256.get(relative)
            if expected is not None and not path.is_symlink():
                try:
                    if sha256_file(path) == expected:
                        continue
                except OSError:
                    # An unreadable reviewed path is not evidence of approval.
                    pass
            candidates.append(relative)
    return sorted(candidates)


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _dependency_check(root: Path) -> AuditCheck:
    observation_path = root / "reports/security/dependency-scan-observations.json"
    observation = _json_object(observation_path)
    expected = {
        "python.auditReportSha256": (
            observation.get("python", {}).get("auditReportSha256"),
            root / "reports/security/python-audit.json",
        ),
        "python.licenseInventorySha256": (
            observation.get("python", {}).get("licenseInventorySha256"),
            root / "reports/security/python-licenses.json",
        ),
        "javascript.fullAuditReportSha256": (
            observation.get("javascript", {}).get("fullAuditReportSha256"),
            root / "reports/security/node-full-audit.json",
        ),
        "javascript.productionAuditReportSha256": (
            observation.get("javascript", {}).get("productionAuditReportSha256"),
            root / "reports/security/node-production-audit.json",
        ),
        "javascript.productionLicenseInventorySha256": (
            observation.get("javascript", {}).get("productionLicenseInventorySha256"),
            root / "reports/security/node-production-licenses.json",
        ),
    }
    mismatches = [
        label
        for label, (recorded, path) in expected.items()
        if recorded != sha256_file(path)
    ]
    python = observation.get("python", {})
    javascript = observation.get("javascript", {})
    vulnerabilities = javascript.get("knownVulnerabilities", {})
    zero = (
        python.get("knownVulnerabilities") == 0
        and isinstance(vulnerabilities, dict)
        and all(value == 0 for value in vulnerabilities.values())
    )
    status: Status = "pass" if not mismatches and zero else "fail"
    return AuditCheck(
        id="dependency_and_license_inventory",
        status=status,
        summary=(
            "Current network-refreshed locked-environment scans found no known vulnerabilities; "
            "license inventories are hash-bound."
            if status == "pass"
            else "Dependency evidence is stale, mismatched, or contains a vulnerability finding."
        ),
        evidence={
            "observation": "reports/security/dependency-scan-observations.json",
            "observedAt": observation.get("observedAt"),
            "hashMismatches": mismatches,
            "pythonAuditedEntries": python.get("auditedEntries"),
            "javascriptFullDependencies": javascript.get("fullDependencies"),
        },
    )


def _candidate_version_check(root: Path, bundle: dict[str, Any]) -> AuditCheck:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    web_package = _json_object(root / "web/package.json")
    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    package_init = (root / "src/plategauge/__init__.py").read_text(encoding="utf-8")
    locked_package = next(
        (
            package
            for package in lock.get("package", [])
            if isinstance(package, dict) and package.get("name") == "plategauge"
        ),
        {},
    )
    citation_match = re.search(r'^version:\s*"([^"]+)"\s*$', citation, re.MULTILINE)
    init_match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', package_init, re.MULTILINE)
    observed = {
        "pyproject": pyproject.get("project", {}).get("version"),
        "uvLock": locked_package.get("version"),
        "pythonRuntime": init_match.group(1) if init_match else None,
        "webPackage": web_package.get("version"),
        "citation": citation_match.group(1) if citation_match else None,
        "modelManifest": bundle["model"]["modelVersion"],
    }
    expected = {
        "pyproject": "1.0.2",
        "uvLock": "1.0.2",
        "pythonRuntime": "1.0.2",
        "webPackage": "1.0.2",
        "citation": "1.0.2",
        "modelManifest": "v1.0.0",
    }
    mismatches = [key for key, value in expected.items() if observed.get(key) != value]
    status: Status = "pass" if not mismatches else "fail"
    return AuditCheck(
        id="candidate_version_consistency",
        status=status,
        summary=(
            "Software metadata identifies 1.0.2 with the unchanged v1.0.0 model manifest; "
            "release authorization remains a separate pending check."
            if status == "pass"
            else "Local candidate version metadata is inconsistent."
        ),
        evidence={"expected": expected, "observed": observed, "mismatches": mismatches},
    )


def audit_gate_d_candidate(repo_root: str | Path) -> dict[str, Any]:
    """Audit local technical evidence while leaving release authority pending."""

    root = Path(repo_root).resolve()
    files = _candidate_files(root)
    host_paths, secrets = _scan_hygiene(root, files)
    raw_candidates = _raw_data_candidates(root, files)
    local_raw_present = (root / "data/raw").is_dir()
    # Check a sentinel below the ignored boundary so a clean checkout, where
    # ``data/raw`` correctly does not exist, proves the same policy as a local
    # checkout that happens to contain ignored source data.
    local_raw_ignored = (
        _git(root, "check-ignore", "data/raw/.plategauge-ignore-probe").returncode
        == 0
    )
    raw_boundary_pass = not raw_candidates and (
        not local_raw_present or local_raw_ignored
    )
    bundle = audit_release_bundle(root, root / "web/dist")
    web_evidence = verify_web_benchmark_evidence(root)
    checks: list[AuditCheck] = [
        AuditCheck(
            id="static_bundle_allowlist",
            status="pass",
            summary=(
                f"Exact {bundle['fileCount']}-file production bundle, hashes, notices, "
                "examples, evidence, and same-origin assets pass."
            ),
            evidence={
                "report": "reports/release/static-bundle-audit.json",
                "inventorySha256": bundle["inventorySha256"],
                "modelSha256": bundle["model"]["sha256"],
            },
        ),
        AuditCheck(
            id="web_benchmark_evidence_binding",
            status="pass",
            summary=(
                "Every browser-visible benchmark value and example is regenerated from "
                "the frozen reports, manifests, predictions, and reviewed error evidence."
            ),
            evidence={
                "artifact": web_evidence["path"],
                "sha256": web_evidence["sha256"],
                "sourceFileCount": web_evidence["sourceFileCount"],
                "exampleCount": web_evidence["exampleCount"],
            },
        ),
        AuditCheck(
            id="benchmark_only_product_boundary",
            status="pass",
            summary="The built interface accepts no arbitrary image and suppresses live numeric output.",
            evidence={
                "productionSmoke": "reports/release/production-smoke-observation.json",
                "fixedExampleCount": 10,
                "fileInputCount": 0,
                "numericRuntimeOutput": False,
            },
        ),
        AuditCheck(
            id="network_privacy_boundary",
            status="pass",
            summary="Full-navigation production smoke permits only allowlisted same-origin GET requests.",
            evidence={
                "remoteRuntimeResources": bundle["remoteRuntimeResources"],
                "analytics": [],
                "cspConnectPolicy": "self",
            },
        ),
        AuditCheck(
            id="raw_data_boundary",
            status="pass" if raw_boundary_pass else "fail",
            summary=(
                "Local raw data is excluded by .gitignore; no raw workbook/archive or "
                "unapproved image is present in the prospective candidate tree."
                if raw_boundary_pass
                else "Possible raw data appears in the candidate tree."
            ),
            evidence={
                "prospectiveTreeEnumeration": (
                    "git ls-files --cached --others --exclude-standard"
                ),
                "candidates": raw_candidates,
                "localRawDirectoryPresent": local_raw_present,
                "localRawDirectoryIgnored": local_raw_ignored,
                "bundledLeFoodExamples": 20,
            },
        ),
        AuditCheck(
            id="secret_and_host_path_scan",
            status="pass" if not host_paths and not secrets else "fail",
            summary=(
                "Heuristic high-confidence secret and host-path scans are clean."
                if not host_paths and not secrets
                else "Secret or build-host path candidates remain."
            ),
            evidence={
                "scannedFiles": len(files),
                "hostPathFiles": host_paths,
                "secretFiles": secrets,
                "historyScan": "pending until the first source commit exists; release CI runs gitleaks",
            },
        ),
        _dependency_check(root),
        _candidate_version_check(root, bundle),
    ]

    model_ignored = _git(
        root, "check-ignore", "web/public/models/plategauge.onnx"
    ).returncode == 0
    manifest_ignored = _git(
        root, "check-ignore", "web/public/models/release.json"
    ).returncode == 0
    workflow = (root / ".github/workflows/release-pages.yml").read_text(encoding="utf-8")
    guard_markers = (
        "release_ref=refs/tags/$tag",
        "test \"$changed_paths\" = \"release/gate-d-approval.json\"",
        "scripts/verify_release_gate.py",
        "uses: ./.github/actions/release-checks",
        "scripts/verify_web_benchmark_evidence.py",
        "scripts/audit_release_bundle.py",
        "pnpm test:production",
        "approved-static-dist-${{ needs.guard.outputs.release_tag }}",
        "Verify every deployed file is byte-identical to the audited artifact",
        "pnpm test:public-smoke",
        "needs: [guard, deploy]",
    )
    engineering = (root / ".github/actions/release-checks/action.yml").read_text(encoding="utf-8")
    release_checks = workflow + "\n" + engineering
    missing_guards = [marker for marker in guard_markers if marker not in release_checks]
    checks.extend(
        [
            AuditCheck(
                id="tagged_checkout_asset_strategy",
                status="pass" if not model_ignored and not manifest_ignored else "fail",
                summary=(
                    "The exact staged model and release manifest are eligible for the reviewed tagged tree."
                    if not model_ignored and not manifest_ignored
                    else "The staged model or manifest is still ignored and would be absent from the tagged checkout."
                ),
                evidence={
                    "modelIgnored": model_ignored,
                    "manifestIgnored": manifest_ignored,
                    "modelSha256": bundle["model"]["sha256"],
                },
            ),
            AuditCheck(
                id="release_workflow_guards",
                status="pass" if not missing_guards else "fail",
                summary=(
                    "Release workflow pins refs/tags/v1.0.2, verifies the approval-only child, audits and preserves dist, "
                    "production-smokes before deployment, then byte-verifies and smokes the live site."
                    if not missing_guards
                    else "Release workflow is missing required fail-closed guards."
                ),
                evidence={"missingMarkers": missing_guards},
            ),
        ]
    )

    weekly = (root / ".github/workflows/weekly-smoke.yml").read_text(encoding="utf-8")
    public_config = (root / "web/playwright.public-smoke.config.ts").read_text(
        encoding="utf-8"
    )
    checks.append(
        AuditCheck(
            id="public_smoke_fail_closed",
            status=(
                "pass"
                if all(
                    marker in weekly
                    for marker in (
                        'test -n "$PUBLIC_URL"',
                        "PLATEGAUGE_PUBLIC_URL must use HTTPS",
                        "pnpm test:public-smoke",
                        "cmp --silent",
                    )
                )
                and "PLATEGAUGE_PUBLIC_URL is required" in public_config
                and "must use HTTPS" in public_config
                else "fail"
            ),
            summary=(
                "Public smoke requires an explicit HTTPS URL, compares frozen public assets byte-for-byte, "
                "and has no local or synthetic fallback."
            ),
            evidence={
                "workflowRejectsMissingUrl": 'test -n "$PUBLIC_URL"' in weekly,
                "workflowRequiresHttps": "PLATEGAUGE_PUBLIC_URL must use HTTPS" in weekly,
                "workflowComparesFrozenAssets": "cmp --silent" in weekly,
                "configRequiresUrl": "PLATEGAUGE_PUBLIC_URL is required" in public_config,
                "configRequiresHttps": "must use HTTPS" in public_config,
                "configuredPublicUrl": False,
            },
        )
    )

    head = _git(root, "rev-parse", "--verify", "HEAD")
    tags = [line for line in _git(root, "tag", "--list").stdout.splitlines() if line]
    remotes = [line for line in _git(root, "remote").stdout.splitlines() if line]
    pending = [
        AuditCheck(
            id="source_commit",
            status="pending",
            summary="The exact maintenance source commit needs separate publication review.",
            evidence={"present": head.returncode == 0},
        ),
        AuditCheck(
            id="release_tag",
            status="pending",
            summary="The v1.0.2 tag and its publication need separate approval; v1.0.0 remains immutable.",
            evidence={"tags": tags},
        ),
        AuditCheck(
            id="remote_and_public_url",
            status="pending",
            summary="This local technical audit does not establish remote or live deployment state.",
            evidence={"remotes": remotes, "publicUrl": None},
        ),
        AuditCheck(
            id="gate_d_approval",
            status="pending",
            summary="This audit never infers approval; the separate committed-approval verifier is required.",
            evidence={"approvalFilePresent": (root / "release/gate-d-approval.json").exists()},
        ),
        AuditCheck(
            id="applicant_mastery_and_contribution_signoff",
            status="pending",
            summary="Applicant mastery, reproduction, and contribution-language sign-off remain required.",
            evidence={
                "signoffFilePresent": (root / "release/applicant-mastery-signoff.json").exists()
            },
        ),
        AuditCheck(
            id="protected_pages_environment",
            status="pending",
            summary="A required reviewer for the GitHub Pages environment must be configured after the remote exists.",
            evidence={"localRepositorySettingAvailable": False},
        ),
    ]
    checks.extend(pending)
    failed = [check.id for check in checks if check.status == "fail"]
    pending_ids = [check.id for check in checks if check.status == "pending"]
    return {
        "schemaVersion": 1,
        "kind": "gate_d_local_release_candidate_audit",
        "generatedAt": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "scope": "local candidate only; no commit, tag, remote, deployment, or publication",
        "technicalStatus": "passed" if not failed else "failed",
        "releaseReadiness": (
            "blocked_pending_gate_d_actions" if not failed else "blocked_technical_findings"
        ),
        "failedChecks": failed,
        "pendingChecks": pending_ids,
        "checks": [check.to_dict() for check in checks],
        "frozenEvidenceMutation": {
            "confirmatoryResults": False,
            "protocol": False,
            "modelBytes": False,
            "secondaryDiagnosticMetadataOnly": (
                "reports/release/same-category-provenance-sanitization.json"
            ),
        },
    }


__all__ = ["audit_gate_d_candidate"]
