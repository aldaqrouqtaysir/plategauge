"""Run the isolated, context-only PlateGauge same-category diagnostic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.data import DEFAULT_AUDIT_REPORT, DEFAULT_DATASET_ROOT, DEFAULT_MANIFEST
from plategauge.errors import PlateGaugeError
from plategauge.orchestration import (
    DEFAULT_EXPERIMENT_CONFIG,
    DEFAULT_FOLDS_CONFIG,
    DEFAULT_RUN_DIRECTORY,
)
from plategauge.same_category_diagnostic import (
    DEFAULT_DIAGNOSTIC_DIRECTORY,
    DEFAULT_SPLIT_CONFIG,
    DEFAULT_SPLIT_REPORT,
    aggregate_same_category_diagnostic,
    fit_same_category_diagnostic,
    preflight_same_category_diagnostic,
)
from plategauge.workloads import ProductionTaskRunner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("preflight", "fit", "aggregate"), default="preflight")
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_EXPERIMENT_CONFIG)
    parser.add_argument("--folds-config", type=Path, default=DEFAULT_FOLDS_CONFIG)
    parser.add_argument("--confirmatory-dir", type=Path, default=DEFAULT_RUN_DIRECTORY)
    parser.add_argument("--split-config", type=Path, default=DEFAULT_SPLIT_CONFIG)
    parser.add_argument("--split-report", type=Path, default=DEFAULT_SPLIT_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIRECTORY)
    parser.add_argument("--checkpoint-root", type=Path, default=Path("artifacts/checkpoints"))
    parser.add_argument("--cache-root", type=Path, default=Path("artifacts/cache"))
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or a Torch device")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    runner = ProductionTaskRunner(
        checkpoint_root=arguments.checkpoint_root,
        cache_root=arguments.cache_root,
        device=arguments.device,
    )
    common = {
        "runner": runner,
        "audit_report_path": arguments.audit_report,
        "manifest_path": arguments.manifest,
        "dataset_root": arguments.dataset_root,
        "config_path": arguments.config,
        "folds_path": arguments.folds_config,
        "confirmatory_directory": arguments.confirmatory_dir,
        "split_path": arguments.split_config,
        "split_report_path": arguments.split_report,
    }
    try:
        if arguments.stage == "preflight":
            payload = preflight_same_category_diagnostic(**common)
        elif arguments.stage == "fit":
            payload = fit_same_category_diagnostic(**common, output_directory=arguments.output_dir)
        else:
            payload = aggregate_same_category_diagnostic(
                **common, output_directory=arguments.output_dir
            )
    except (PlateGaugeError, OSError, ValueError, TypeError) as exc:
        print(
            json.dumps({"error": type(exc).__name__, "message": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
