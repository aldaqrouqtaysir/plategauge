"""Derive the declared post-hoc visual-discordance sensitivity report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.errors import PlateGaugeError
from plategauge.label_sensitivity import build_label_sensitivity_report
from plategauge.orchestration import DEFAULT_RUN_DIRECTORY

DEFAULT_EXCLUSIONS = ("lefood-0320", "lefood-0400", "lefood-0507", "lefood-0530")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIRECTORY)
    parser.add_argument(
        "--exclude",
        action="append",
        dest="exclusions",
        help="Sample ID to omit. Repeat to declare multiple IDs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/label_sensitivity.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    exclusions = tuple(arguments.exclusions or DEFAULT_EXCLUSIONS)
    try:
        report = build_label_sensitivity_report(
            run_directory=arguments.run_dir,
            excluded_sample_ids=exclusions,
            output_path=arguments.output,
        )
    except (PlateGaugeError, OSError, ValueError) as exc:
        print(
            json.dumps({"error": type(exc).__name__, "message": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(arguments.output),
                "excluded_sample_ids": report["excluded_sample_ids"],
                "direction_reversed": report["conclusion"]["direction_reversed"],
                "evidence_sha256": report["evidence_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
