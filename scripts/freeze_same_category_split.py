"""Freeze the preregistered secondary same-category diagnostic assignment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from plategauge.same_category_split import (
    build_split_artifact,
    sha256_file,
    validate_split_artifact,
    write_immutable_json,
)


def _outer_result_paths(run_directory: Path) -> list[str]:
    if not run_directory.exists():
        return []
    paths: list[str] = []
    for path in run_directory.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(run_directory).as_posix()
        parts = relative.split("/")
        if any(part.startswith(("outer-", "outer_", "outer.")) for part in parts):
            paths.append(relative)
    return sorted(paths)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/lefood_v1_manifest.csv")
    )
    parser.add_argument(
        "--run", type=Path, default=Path("reports/experiments/confirmatory/run.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("configs/same_category_folds_v1.json")
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/data_gate/same_category_folds_v1_validation.json"),
    )
    arguments = parser.parse_args()

    outer_paths = _outer_result_paths(arguments.run.parent)
    if outer_paths:
        raise SystemExit(
            "Refusing to freeze the diagnostic split after outer result artifacts exist: "
            + ", ".join(outer_paths[:5])
        )

    artifact = build_split_artifact(arguments.manifest, arguments.run)
    write_immutable_json(arguments.output, artifact)
    loaded = json.loads(arguments.output.read_text(encoding="utf-8"))
    validation = validate_split_artifact(loaded, arguments.manifest, arguments.run)
    validation.update(
        {
            "config_path": arguments.output.as_posix(),
            "config_sha256": sha256_file(arguments.output),
            "frozen_before_outer_results": True,
            "outer_result_artifact_count_at_freeze": 0,
            "outer_result_paths_at_freeze": [],
        }
    )
    write_immutable_json(arguments.report, validation)
    print(json.dumps(validation, indent=2, sort_keys=True))
    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
