"""Generate or verify Python/browser preprocessing golden fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from plategauge.preprocess_contract import generate_preprocess_golden, verify_preprocess_golden


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("web/tests/fixtures/preprocess-golden"),
    )
    arguments = parser.parse_args()
    payload = (
        generate_preprocess_golden(arguments.directory)
        if arguments.mode == "generate"
        else verify_preprocess_golden(arguments.directory)
    )
    print(
        json.dumps(
            {
                "directory": str(arguments.directory),
                "fixture_count": len(payload["fixtures"]),
                "evidence_sha256": payload["evidence_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
