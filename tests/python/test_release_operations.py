"""Synthetic discovery tests; never run a model, access data, or deploy."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/verify_release_operations.py"
SPEC = importlib.util.spec_from_file_location("release_operations", SCRIPT)
assert SPEC and SPEC.loader
operations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operations)


class ReleaseOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "release").mkdir()

    def profile(self, name: str) -> Path:
        path = self.root / "release" / name
        path.mkdir()
        for file in operations.REQUIRED_FILES:
            (path / file).write_text("synthetic fixture", encoding="utf-8")
        return path

    def test_discovers_existing_and_new_numbered_profiles(self) -> None:
        for name in ("camera", "camera-r2", "camera-r3", "camera-r4"):
            self.profile(name)
        self.assertEqual(len(operations.discover_profiles(self.root)), 4)

    def test_empty_scope_is_not_a_pass(self) -> None:
        with self.assertRaises(ValueError):
            operations.discover_profiles(self.root)

    def test_missing_file_is_rejected(self) -> None:
        path = self.profile("camera-r3")
        (path / "live.spec.ts").unlink()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            operations.discover_profiles(self.root)

    def test_unexpected_names_are_rejected(self) -> None:
        self.profile("camera-latest")
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            operations.discover_profiles(self.root)

    def test_profile_count_is_bounded(self) -> None:
        self.profile("camera")
        with patch.object(operations, "MAX_PROFILES", 0), self.assertRaises(ValueError):
            operations.discover_profiles(self.root)

    def test_links_and_junctions_are_rejected(self) -> None:
        self.profile("camera")
        for method in ("is_symlink", "is_junction"):
            with patch.object(Path, method, return_value=True), self.assertRaises(ValueError):
                operations.discover_profiles(self.root)

    def test_checks_are_isolated_without_shell_or_model_calls(self) -> None:
        self.profile("camera")
        self.profile("camera-r4")
        with patch.object(subprocess, "run") as run:
            operations.run_checks(self.root, "synthetic")
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertIn("unittest", call.args[0])
                self.assertEqual(call.kwargs, {"cwd": self.root, "check": True, "timeout": 600})
        with patch.object(subprocess, "run") as run:
            operations.run_checks(self.root, "typing")
            self.assertEqual(run.call_count, 6)

    def test_process_failure_is_not_suppressed(self) -> None:
        self.profile("camera")
        with (
            patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, "synthetic")),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            operations.run_checks(self.root, "synthetic")

    def test_bot_preserves_current_frozen_and_reserved_successor_workflows(self) -> None:
        root = SCRIPT.parents[1]
        config = (root / ".github/dependabot.yml").read_text(encoding="utf-8")
        self.assertIn("package-ecosystem: uv", config)
        self.assertNotIn("package-ecosystem: pip", config)
        self.assertIn("exclude-paths:", config)
        for profile in ("", "-r2", "-r3", "-r4"):
            for prefix, suffix in (("release", "pages"), ("rollback", "pages"), ("weekly", "smoke")):
                self.assertIn(f".github/workflows/{prefix}-camera{profile}-{suffix}.yml", config)
        self.assertNotIn(".github/workflows/*", config)


if __name__ == "__main__":
    unittest.main()
