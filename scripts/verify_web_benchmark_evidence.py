"""Generate or verify the browser's frozen benchmark evidence payload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.errors import PlateGaugeError
from plategauge.web_evidence import (
    DEFAULT_OUTPUT,
    verify_web_benchmark_evidence,
    write_web_benchmark_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args(argv)
    try:
        report = (
            write_web_benchmark_evidence(arguments.repo_root, arguments.artifact)
            if arguments.mode == "generate"
            else verify_web_benchmark_evidence(arguments.repo_root, arguments.artifact)
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
