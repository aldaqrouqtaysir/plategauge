"""Stage validated frozen release assets for a local/static web build."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.errors import PlateGaugeError
from plategauge.release_staging import stage_web_release


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-evidence",
        type=Path,
        default=Path("artifacts/plategauge.onnx.evidence.json"),
    )
    parser.add_argument("--results", type=Path, default=Path("reports/results.json"))
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("web/public/models"),
    )
    parser.add_argument("--model-version", required=True)
    arguments = parser.parse_args(argv)
    try:
        report = stage_web_release(
            evidence_path=arguments.release_evidence,
            results_path=arguments.results,
            output_directory=arguments.output_directory,
            model_version=arguments.model_version,
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
