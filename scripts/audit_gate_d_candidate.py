"""Write the local, non-deploying Gate D release-candidate audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.errors import PlateGaugeError
from plategauge.gate_d_audit import audit_gate_d_candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/release/gate-d-local-candidate-audit.json"),
    )
    arguments = parser.parse_args(argv)
    try:
        report = audit_gate_d_candidate(arguments.repo_root)
        output = arguments.output
        if not output.is_absolute():
            output = arguments.repo_root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    except (PlateGaugeError, OSError, ValueError) as exc:
        print(
            json.dumps({"status": "blocked", "error": type(exc).__name__, "message": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["technicalStatus"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
