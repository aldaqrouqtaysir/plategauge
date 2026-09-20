"""Create portable, deterministic local review packages for the release gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.errors import PlateGaugeError
from plategauge.review_package import (
    DEFAULT_REVIEW_DELIVERABLES,
    create_gate_d_review_package,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-directory",
        type=Path,
        help="Private review-output directory; defaults to a sibling outputs directory.",
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Stable package date in YYYY-MM-DD form.",
    )
    parser.add_argument(
        "--review-deliverable",
        action="append",
        dest="review_deliverables",
        help="Review filename in the output directory; repeat to override the default set.",
    )
    arguments = parser.parse_args(argv)
    root = arguments.repo_root.resolve()
    output_directory = (
        arguments.output_directory.resolve()
        if arguments.output_directory is not None
        else root.parent / "outputs"
    )
    review_deliverables = arguments.review_deliverables or list(DEFAULT_REVIEW_DELIVERABLES)
    try:
        report = create_gate_d_review_package(
            root,
            output_directory,
            arguments.date,
            review_deliverables,
        )
    except (PlateGaugeError, OSError, ValueError) as exc:
        print(
            json.dumps({"status": "blocked", "error": type(exc).__name__, "message": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
