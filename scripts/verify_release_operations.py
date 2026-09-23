"""Run bounded synthetic/type checks for preserved camera release profiles."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PROFILE_NAME = re.compile(r"camera(?:-r[1-9][0-9]{0,2})?\Z")
MAX_PROFILES = 16
REQUIRED_FILES = (
    "verify_release.py",
    "test_verify_release.py",
    "tsconfig.json",
    "live-support.ts",
    "live.spec.ts",
    "playwright.live.config.ts",
)


def discover_profiles(root: Path) -> list[Path]:
    """Never accept arbitrary globs, linked profiles, or an empty passing scope."""
    root = root.resolve(strict=True)
    release = root / "release"
    if release.is_symlink() or release.is_junction() or not release.is_dir():
        raise ValueError("Release root must be an ordinary directory")
    candidates = sorted(release.glob("camera*"))
    if not 1 <= len(candidates) <= MAX_PROFILES:
        raise ValueError("Expected a bounded nonempty camera profile set")
    for path in candidates:
        if (
            not PROFILE_NAME.fullmatch(path.name)
            or path.is_symlink()
            or path.is_junction()
            or not path.is_dir()
        ):
            raise ValueError(f"Unexpected camera profile: {path.name}")
        for name in REQUIRED_FILES:
            file = path / name
            if file.is_symlink() or file.is_junction() or not file.is_file():
                raise ValueError(f"Incomplete or linked camera profile: {path.name}/{name}")
    return candidates


def run_checks(root: Path, phase: str) -> None:
    profiles = discover_profiles(root)
    for profile in profiles:
        relative = profile.relative_to(root).as_posix()
        if phase == "synthetic":
            commands = [[sys.executable, "-m", "unittest", "discover", "-s", relative,
                         "-p", "test_verify_release.py", "-v"]]
        elif phase == "typing":
            commands = [
                [sys.executable, "-m", "ruff", "check", relative],
                [sys.executable, "-m", "mypy", "--strict", f"{relative}/verify_release.py",
                 f"{relative}/test_verify_release.py"],
                ["node", "web/node_modules/typescript/bin/tsc", "--project", f"{relative}/tsconfig.json"],
            ]
        else:
            raise ValueError("Unknown check phase")
        print(f"{phase}: {relative}", flush=True)
        for command in commands:
            subprocess.run(command, cwd=root, check=True, timeout=600)
    print(f"Passed {phase} checks for {len(profiles)} camera release profiles", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--phase", choices=("synthetic", "typing"), required=True)
    args = parser.parse_args()
    run_checks(args.repo_root.resolve(strict=True), args.phase)


if __name__ == "__main__":
    main()
