"""Validate a real reference-laptop measurement and evaluate browser gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from plategauge.browser_benchmark import evaluate_browser_benchmark_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate supplied measurements; this command never synthesizes benchmark data."
    )
    parser.add_argument("measurement", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--release-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/browser_benchmark.json"))
    arguments = parser.parse_args()
    report = evaluate_browser_benchmark_files(
        measurement_path=arguments.measurement,
        model_path=arguments.model,
        release_evidence_path=arguments.release_evidence,
        output_path=arguments.output,
    )
    print(
        json.dumps(
            {
                "output": str(arguments.output),
                "status": report["status"],
                "warm_p95_ms": report["derived"]["warm_p95_ms"],
                "peak_application_memory_mb": report["reported"]["peak_application_memory_mb"],
                "evidence_sha256": report["evidence_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
