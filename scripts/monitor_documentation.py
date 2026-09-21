"""Bound documentation checks to tracked project files; never turn errors into passes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

EXCLUDED_PARTS = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        "__pycache__",
        "test-results",
        "playwright-report",
    }
)
COUNTERS = (
    "total",
    "successful",
    "unknown",
    "unsupported",
    "timeouts",
    "excludes",
    "errors",
    "cached",
)


def tracked_markdown(root: Path) -> tuple[list[str], list[str]]:
    """Git's NUL-separated index is authoritative, not a recursive filesystem glob."""
    root = root.resolve(strict=True)
    raw = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "-z"],
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout
    selected: list[str] = []
    excluded: list[str] = []
    for name in sorted(set(raw.decode("utf-8").rstrip("\0").split("\0"))):
        if not name.lower().endswith(".md"):
            continue
        # --files-from also accepts URLs/globs/comments. Accept only unambiguous
        # relative filenames; spaces are supported without shell interpolation.
        path = PurePosixPath(name)
        if not re.fullmatch(r"[A-Za-z0-9_./ -]+", name) or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe documentation input: {name!r}")
        if EXCLUDED_PARTS.intersection(path.parts):
            excluded.append(name)
            continue
        local = root / name
        if any(part.is_symlink() for part in (local, *local.parents) if part != root.parent):
            raise ValueError(f"Symlink documentation input: {name!r}")
        if not local.resolve(strict=True).is_relative_to(root) or not local.is_file():
            raise ValueError(f"Missing or escaping documentation input: {name!r}")
        selected.append(name)
    if not selected:
        raise ValueError("No tracked project Markdown files; an empty scan cannot pass")
    return selected, excluded


def prepare_inputs(root: Path, destination: Path) -> dict[str, Any]:
    root, destination = root.resolve(strict=True), destination.resolve(strict=True)
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("Diagnostics must be outside and separate from source")
    if not destination.is_dir() or any(destination.iterdir()):
        raise ValueError("Diagnostics directory must be empty; refuse stale evidence")
    selected, excluded = tracked_markdown(root)
    records = [
        {"path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
        for name in selected
    ]
    manifest = {
        "files": records,
        "excludedTrackedPaths": excluded,
        "scope": "tracked project Markdown",
    }
    # Prefix ./ prevents a filename being interpreted as a URL, option or comment.
    (destination / "inputs.txt").write_text(
        "".join(f"./{name}\n" for name in selected), encoding="utf-8", newline="\n"
    )
    (destination / "inputs.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def classify_report(raw: Any, checker_exit: int) -> dict[str, Any]:
    """Interpret pinned Lychee JSON conservatively; raw diagnostics are retained."""
    if not isinstance(raw, dict):
        raise ValueError("Checker report is not an object")
    for key in COUNTERS:
        if type(raw.get(key)) is not int or raw[key] < 0:
            raise ValueError(f"Missing or invalid checker counter: {key}")
    if raw["total"] != sum(raw[key] for key in COUNTERS[1:-1]):
        raise ValueError("Inconsistent checker totals")
    findings: list[dict[str, Any]] = []
    for field in ("error_map", "timeout_map"):
        mapping = raw.get(field)
        if not isinstance(mapping, dict):
            raise ValueError(f"Missing or invalid {field}")
        for source, records in mapping.items():
            if not isinstance(source, str) or not isinstance(records, list):
                raise ValueError("Malformed checker map")
            for record in records:
                if not isinstance(record, dict) or not isinstance(record.get("url"), str):
                    raise ValueError("Malformed checker finding")
                status = record.get("status")
                if not isinstance(status, dict) or not isinstance(status.get("text"), str):
                    raise ValueError("Malformed checker status")
                code = status.get("code")
                if code is not None and (type(code) is not int or not 100 <= code <= 599):
                    raise ValueError("Invalid HTTP status")
                if field == "timeout_map":
                    category = "timeout"
                elif code in (401, 403, 429):
                    category = "blocked_or_rate_limited"
                elif code in (404, 410):
                    category = "broken_reference"
                elif code is not None and code >= 500:
                    category = "upstream_error"
                else:
                    category = "other_error"
                findings.append({"source": source, "category": category, **record})
    error_count = sum(len(items) for items in raw["error_map"].values())
    timeout_count = sum(len(items) for items in raw["timeout_map"].values())
    if error_count != raw["errors"] or timeout_count != raw["timeouts"]:
        raise ValueError("Counters disagree with retained findings")
    passed = (
        checker_exit == 0
        and raw["successful"] > 0
        and all(raw[key] == 0 for key in ("errors", "timeouts", "unknown", "unsupported"))
    )
    return {
        "status": "passed" if passed else "failed",
        "checkerExitCode": checker_exit,
        "scope": "documentation only; not application availability or scientific validation",
        "counts": {key: raw[key] for key in COUNTERS},
        "classifications": dict(sorted(Counter(item["category"] for item in findings).items())),
        "findings": findings,
        "excludedLinksAreNotVerified": True,
        "cachedCountMayIncludeWithinRunDeduplication": True,
    }


def summarize(report: Path, destination: Path, checker_exit: str) -> dict[str, Any]:
    """Missing, timed-out, invalid or empty output fails with a structured diagnostic."""
    try:
        result = classify_report(
            json.loads(report.read_text(encoding="utf-8-sig")), int(checker_exit)
        )
    except (OSError, ValueError, TypeError) as error:
        result = {"status": "checker_error", "reason": str(error), "scope": "documentation only"}
    output = destination / "classification.json"
    if output.exists():
        raise ValueError("Classification already exists; refusing stale diagnostics")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--repo-root", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    summary = subparsers.add_parser("summarize")
    summary.add_argument("--report", type=Path, required=True)
    summary.add_argument("--output-dir", type=Path, required=True)
    summary.add_argument("--checker-exit", required=True)
    args = parser.parse_args()
    if args.operation == "prepare":
        result = prepare_inputs(args.repo_root, args.output_dir)
        print(f"Selected {len(result['files'])} tracked project Markdown files")
        return 0
    result = summarize(args.report, args.output_dir, args.checker_exit)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
