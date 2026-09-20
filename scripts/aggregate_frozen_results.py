"""Build frozen PlateGauge result reports from immutable outer artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.data import DEFAULT_AUDIT_REPORT, DEFAULT_MANIFEST
from plategauge.errors import PlateGaugeError
from plategauge.orchestration import (
    DEFAULT_EXPERIMENT_CONFIG,
    DEFAULT_FOLDS_CONFIG,
    DEFAULT_RUN_DIRECTORY,
)
from plategauge.post_evaluation import build_frozen_reports


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIRECTORY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--config", type=Path, default=DEFAULT_EXPERIMENT_CONFIG)
    parser.add_argument("--folds-config", type=Path, default=DEFAULT_FOLDS_CONFIG)
    parser.add_argument("--results", type=Path, default=Path("reports/results.json"))
    parser.add_argument(
        "--bootstrap",
        type=Path,
        default=Path("reports/bootstrap_comparisons.json"),
    )
    parser.add_argument(
        "--efficiency-evidence",
        type=Path,
        help="optional schema-1.0 JSON binding ONNX size/hash and parity drift",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        results, bootstrap = build_frozen_reports(
            run_directory=arguments.run_dir,
            manifest_path=arguments.manifest,
            audit_report_path=arguments.audit_report,
            config_path=arguments.config,
            folds_path=arguments.folds_config,
            results_path=arguments.results,
            bootstrap_path=arguments.bootstrap,
            efficiency_evidence_path=arguments.efficiency_evidence,
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
                "status": "complete",
                "results": str(arguments.results),
                "bootstrap": str(arguments.bootstrap),
                "run_id": results["run_id"],
                "release_recommendation": results["decisions"]["release_recommendation"],
                "comparisons": list(bootstrap["comparisons"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
