"""Synthetic discovery tests; never run a model, access data, or deploy."""

from __future__ import annotations

import importlib.util
import re
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

    def assert_bot_preservation(self, config: str, profiles: list[Path]) -> None:
        """Check the narrow YAML block without adding a runtime YAML dependency."""
        self.assertIn("package-ecosystem: uv", config)
        self.assertNotIn("package-ecosystem: pip", config)
        marker = "  - package-ecosystem: github-actions\n"
        self.assertEqual(config.count(marker), 1)
        actions = config.split(marker)[1].split("\n  - package-ecosystem:", 1)[0]
        block = re.search(r"(?ms)^    exclude-paths:\n(.*?)(?=^    \S|\Z)", actions)
        self.assertIsNotNone(block, "GitHub Actions needs its own preservation block")
        assert block is not None
        entries = [
            line.strip() for line in block.group(1).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(entries and all(line.startswith("- ") for line in entries))
        paths = [line[2:] for line in entries]
        self.assertEqual(len(paths), len(set(paths)), "Duplicate preservation paths")
        # Exact reserved successor names remain possible before their profile exists.
        # Ordinary CI/monitoring and wildcard scopes must not be excluded.
        allowed = re.compile(
            r"^\.github/workflows/(?:release-pages|"
            r"(?:release|rollback)-camera(?:-r[1-9][0-9]{0,2})?-pages|"
            r"weekly-camera(?:-r[1-9][0-9]{0,2})?-smoke)\.yml\Z"
        )
        for path in paths:
            self.assertRegex(path, allowed)
        required = {".github/workflows/release-pages.yml"}
        for profile in profiles:
            revision = profile.name.removeprefix("camera")
            for prefix, suffix in (("release", "pages"), ("rollback", "pages"), ("weekly", "smoke")):
                required.add(f".github/workflows/{prefix}-camera{revision}-{suffix}.yml")
        self.assertTrue(required.issubset(paths), f"Missing preservation paths: {required - set(paths)}")

    def test_bot_preserves_current_frozen_and_reserved_successor_workflows(self) -> None:
        root = SCRIPT.parents[1]
        config = (root / ".github/dependabot.yml").read_text(encoding="utf-8")
        self.assert_bot_preservation(config, operations.discover_profiles(root))

    def test_bot_policy_rejects_missing_legacy_and_recent_release_paths(self) -> None:
        root = SCRIPT.parents[1]
        config = (root / ".github/dependabot.yml").read_text(encoding="utf-8")
        profiles = operations.discover_profiles(root)
        paths = [".github/workflows/release-pages.yml"] + [
            f".github/workflows/{prefix}-camera-{revision}-{suffix}.yml"
            for revision in ("r5", "r6")
            for prefix, suffix in (("release", "pages"), ("rollback", "pages"), ("weekly", "smoke"))
        ]
        for path in paths:
            with self.subTest(path=path):
                row = f"      - {path}\n"
                self.assertIn(row, config)
                with self.assertRaises(AssertionError):
                    self.assert_bot_preservation(config.replace(row, "", 1), profiles)

    def test_bot_policy_rejects_wildcards_and_ordinary_workflow_exclusions(self) -> None:
        root = SCRIPT.parents[1]
        config = (root / ".github/dependabot.yml").read_text(encoding="utf-8")
        profiles = operations.discover_profiles(root)
        for path in (
            ".github/workflows/*", ".github/workflows/release-camera-*.yml",
            ".github/workflows/**/action.yml", ".github/workflows/weekly-*.yml",
            "**/.github/workflows/release-pages.yml",
            ".github/workflows/ci.yml", ".github/workflows/weekly-smoke.yml",
        ):
            with self.subTest(path=path), self.assertRaises(AssertionError):
                changed = config.replace("    exclude-paths:\n", f"    exclude-paths:\n      - {path}\n")
                self.assert_bot_preservation(changed, profiles)

    def test_bot_policy_rejects_duplicate_exclusions(self) -> None:
        root = SCRIPT.parents[1]
        config = (root / ".github/dependabot.yml").read_text(encoding="utf-8")
        changed = config.replace(
            "    exclude-paths:\n",
            "    exclude-paths:\n      - .github/workflows/release-pages.yml\n",
        )
        with self.assertRaises(AssertionError):
            self.assert_bot_preservation(changed, operations.discover_profiles(root))

    def test_bot_policy_tracks_discovered_profiles_and_allows_exact_reservations(self) -> None:
        root = SCRIPT.parents[1]
        config = (root / ".github/dependabot.yml").read_text(encoding="utf-8")
        profiles = operations.discover_profiles(root)
        revision = 1 + max(
            int(path.name.removeprefix("camera-r"))
            for path in profiles if path.name != "camera"
        )
        successor = self.profile(f"camera-r{revision}")
        with self.assertRaises(AssertionError):
            self.assert_bot_preservation(config, [*profiles, successor])
        reservations = "".join(
            f"      - .github/workflows/{prefix}-camera-r{revision}-{suffix}.yml\n"
            for prefix, suffix in (("release", "pages"), ("rollback", "pages"), ("weekly", "smoke"))
        )
        changed = config.replace("    exclude-paths:\n", "    exclude-paths:\n" + reservations)
        self.assert_bot_preservation(changed, profiles)
        self.assert_bot_preservation(changed, [*profiles, successor])


if __name__ == "__main__":
    unittest.main()
