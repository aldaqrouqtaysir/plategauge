"""Derive the immutable Gate C error ledger from frozen outer predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.data import DEFAULT_AUDIT_REPORT, DEFAULT_MANIFEST
from plategauge.error_analysis import build_error_analysis_report
from plategauge.errors import PlateGaugeError
from plategauge.orchestration import (
    DEFAULT_EXPERIMENT_CONFIG,
    DEFAULT_FOLDS_CONFIG,
    DEFAULT_RUN_DIRECTORY,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIRECTORY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--config", type=Path, default=DEFAULT_EXPERIMENT_CONFIG)
    parser.add_argument("--folds-config", type=Path, default=DEFAULT_FOLDS_CONFIG)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/error_analysis.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = build_error_analysis_report(
            run_directory=arguments.run_dir,
            manifest_path=arguments.manifest,
            audit_report_path=arguments.audit_report,
            config_path=arguments.config,
            folds_path=arguments.folds_config,
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
                "run_id": report["run_id"],
                "record_count": report["dataset"]["valid_pairs"],
                "largest_error_records": len(
                    report["largest_absolute_errors"]["records"]
                ),
                "smallest_error_records": len(
                    report["smallest_absolute_errors"]["records"]
                ),
                "evidence_sha256": report["evidence_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
