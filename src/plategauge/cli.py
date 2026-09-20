"""Command-line interface for reproducible audits and frozen-result evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .data import (
    DEFAULT_AUDIT_REPORT,
    DEFAULT_DATASET_ROOT,
    DEFAULT_DUPLICATE_REVIEW,
    DEFAULT_MANIFEST,
    DEFAULT_SOURCE_AUDIT,
    audit_manifest_file,
    create_and_audit_lefood_artifacts,
)
from .errors import PlateGaugeError
from .evaluation import evaluate_predictions, numeric_demo_gate, read_predictions
from .features import extract_handcrafted_features, handcrafted_feature_names
from .orchestration import (
    DEFAULT_EXPERIMENT_CONFIG,
    DEFAULT_FOLDS_CONFIG,
    DEFAULT_RUN_DIRECTORY,
    CommandTaskRunner,
    execute_experiment,
    parse_worker_command,
    protocol_preflight,
)
from .schema import read_manifest
from .workloads import ProductionTaskRunner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plategauge", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-manifest", help="reproduce LeFood metadata artifacts")
    build.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    build.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    build.add_argument("--source-audit", type=Path, default=DEFAULT_SOURCE_AUDIT)
    build.add_argument("--report", type=Path, default=DEFAULT_AUDIT_REPORT)
    build.add_argument("--duplicate-review", type=Path, default=DEFAULT_DUPLICATE_REVIEW)
    build.add_argument(
        "--skip-near-duplicates",
        action="store_true",
        help="development-only shortcut; release manifests must not use it",
    )

    audit = subparsers.add_parser("audit-data", help="validate an existing manifest")
    audit.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    audit.add_argument("--dataset-root", type=Path)
    audit.add_argument("--verify-hashes", action="store_true")

    features = subparsers.add_parser("features", help="print handcrafted features for one pair")
    features.add_argument("before", type=Path)
    features.add_argument("after", type=Path)

    metrics = subparsers.add_parser("evaluate", help="evaluate a frozen prediction CSV")
    metrics.add_argument("predictions", type=Path)
    metrics.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)

    experiment = subparsers.add_parser(
        "run-experiment", help="run the gated nested-CV experiment or report its blocker"
    )
    experiment.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    experiment.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    experiment.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    experiment.add_argument("--config", type=Path, default=DEFAULT_EXPERIMENT_CONFIG)
    experiment.add_argument("--folds-config", type=Path, default=DEFAULT_FOLDS_CONFIG)
    experiment.add_argument("--output-dir", type=Path, default=DEFAULT_RUN_DIRECTORY)
    experiment.add_argument(
        "--stage",
        choices=("preflight", "inner", "select", "outer", "final", "all"),
        default="preflight",
        help="explicit information-boundary stage; defaults to read-only preflight",
    )
    experiment.add_argument(
        "--worker",
        type=Path,
        help="optional pinned external worker executable; defaults to the in-repo runner",
    )
    experiment.add_argument(
        "--worker-arg",
        action="append",
        default=[],
        help="repeatable argument inserted before the worker JSON contract paths",
    )
    experiment.add_argument(
        "--checkpoint-root", type=Path, default=Path("artifacts/checkpoints")
    )
    experiment.add_argument("--cache-root", type=Path, default=Path("artifacts/cache"))
    experiment.add_argument("--device", default="auto", help="auto, cpu, cuda, or a Torch device")
    experiment.add_argument(
        "--dry-run",
        action="store_true",
        help="backward-compatible alias for --stage preflight",
    )

    subparsers.add_parser("doctor", help="show optional dependency availability")
    return parser


def _evaluate_csv(path: Path, manifest_path: Path) -> dict[str, object]:
    evaluation = evaluate_predictions(read_predictions(path), read_manifest(manifest_path))
    evaluation["numeric_demo_gate_passed"] = numeric_demo_gate(evaluation)
    return evaluation


def _doctor() -> dict[str, object]:
    import importlib.util

    packages = ("numpy", "PIL", "openpyxl", "torch", "timm", "onnx", "onnxruntime")
    return {
        "plategauge_version": __version__,
        "python": sys.version.split()[0],
        "dependencies": {name: importlib.util.find_spec(name) is not None for name in packages},
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "build-manifest":
            report = create_and_audit_lefood_artifacts(
                arguments.dataset_root,
                manifest_path=arguments.manifest,
                source_audit_path=arguments.source_audit,
                report_path=arguments.report,
                duplicate_review_path=arguments.duplicate_review,
                detect_near_duplicates=not arguments.skip_near_duplicates,
            )
            payload = report.to_dict()
        elif arguments.command == "audit-data":
            payload = audit_manifest_file(
                arguments.manifest,
                dataset_root=arguments.dataset_root,
                verify_hashes=arguments.verify_hashes,
            ).to_dict()
        elif arguments.command == "features":
            values = extract_handcrafted_features(arguments.before, arguments.after)
            payload = dict(zip(handcrafted_feature_names(), values.tolist(), strict=True))
        elif arguments.command == "evaluate":
            payload = _evaluate_csv(arguments.predictions, arguments.manifest)
        elif arguments.command == "run-experiment":
            if arguments.dry_run or arguments.stage == "preflight":
                preflight, _ = protocol_preflight(
                    audit_report_path=arguments.audit_report,
                    manifest_path=arguments.manifest,
                    config_path=arguments.config,
                    folds_path=arguments.folds_config,
                )
                payload = preflight.to_dict()
            else:
                runner = (
                    ProductionTaskRunner(
                        checkpoint_root=arguments.checkpoint_root,
                        cache_root=arguments.cache_root,
                        device=arguments.device,
                    )
                    if arguments.worker is None
                    else CommandTaskRunner(
                        parse_worker_command(arguments.worker, arguments.worker_arg)
                    )
                )
                payload = execute_experiment(
                    audit_report_path=arguments.audit_report,
                    manifest_path=arguments.manifest,
                    dataset_root=arguments.dataset_root,
                    output_directory=arguments.output_dir,
                    runner=runner,
                    stage=arguments.stage,
                    config_path=arguments.config,
                    folds_path=arguments.folds_config,
                ).to_dict()
        else:
            payload = _doctor()
        print(json.dumps(payload, indent=2, sort_keys=True))
        succeeded = bool(payload.get("passed", True)) and payload.get("status") != "blocked"
        return 0 if succeeded else 2
    except (PlateGaugeError, OSError, ValueError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
