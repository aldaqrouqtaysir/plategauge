"""Print the reproducible, non-binding duplicate-safe fold proposal."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from plategauge.errors import DataIntegrityError
from plategauge.fold_amendment import ADVISORY_STATUS, build_fold_amendment_proposal

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify frozen data-gate inputs and print the non-binding fold-amendment "
            "candidate. This command never writes or activates a split."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="PlateGauge checkout to verify (default: the checkout containing this script)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        proposal = build_fold_amendment_proposal(args.repo_root)
    except DataIntegrityError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(proposal, indent=2) + "\n", end="")
    print(
        f"{ADVISORY_STATUS}: advisory printed; frozen inputs and active folds were not changed.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
