"""Create a fresh diagnostics directory outside the prospective source tree."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def prepare_diagnostics(repo_root: Path, temp_root: Path, scope: str) -> Path:
    """Reject in-tree/overlapping destinations and never reuse prior diagnostics."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", scope):
        raise ValueError("Diagnostic scope must be a bounded path-free identifier")
    root = repo_root.resolve(strict=True)
    temporary = temp_root.resolve(strict=True)
    if not root.is_dir() or not temporary.is_dir():
        raise ValueError("Source and temporary roots must be directories")
    destination = temporary / f"plategauge-diagnostics-{scope}"
    resolved = destination.resolve()
    if resolved.is_relative_to(root) or root.is_relative_to(resolved):
        raise ValueError("Diagnostic directory must be outside and separate from source")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Diagnostic directory already exists; refusing stale evidence")
    destination.mkdir()
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--temp-root", type=Path, required=True)
    parser.add_argument("--scope", required=True)
    args = parser.parse_args()
    print(prepare_diagnostics(args.repo_root, args.temp_root, args.scope))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
