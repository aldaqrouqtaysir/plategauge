"""Generate immutable, accessible SVG figures from frozen Gate C reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.data import sha256_file
from plategauge.errors import PlateGaugeError
from plategauge.gate_c_figures import generate_gate_c_figures
from plategauge.orchestration import DEFAULT_RUN_DIRECTORY


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("reports/results.json"))
    parser.add_argument("--robustness", type=Path, default=Path("reports/robustness.json"))
    parser.add_argument(
        "--run-descriptor",
        type=Path,
        default=DEFAULT_RUN_DIRECTORY / "run.json",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports/figures"))
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        paths = generate_gate_c_figures(
            results_path=arguments.results,
            robustness_path=arguments.robustness,
            run_descriptor_path=arguments.run_descriptor,
            output_directory=arguments.output_dir,
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
                "figures": [{"path": str(path), "sha256": sha256_file(path)} for path in paths],
                "status": "complete",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
