"""Synthetic regressions for the release diagnostics/source boundary."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from plategauge.gate_d_audit import _candidate_files, _scan_hygiene
from scripts.prepare_release_diagnostics import prepare_diagnostics


class ReleaseDiagnosticsTests(unittest.TestCase):
    def test_fresh_directory_outside_source_and_refuse_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "source"
            root.mkdir()
            diagnostic = prepare_diagnostics(root, base, "123-1-build")
            self.assertFalse(diagnostic.is_relative_to(root))
            self.assertTrue(diagnostic.is_dir())
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare_diagnostics(root, base, "123-1-build")

    def test_in_tree_temporary_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "outside"):
                prepare_diagnostics(root, root, "build")
            nested = root / "nested"
            nested.mkdir()
            with self.assertRaisesRegex(ValueError, "outside"):
                prepare_diagnostics(root, nested, "build")
            self.assertEqual(list(nested.iterdir()), [])

    def test_scope_cannot_escape_or_inject_environment_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for scope in ("", "..", "../source", "a/b", "a\\b", "a:b", "x\nTOKEN=x", "x" * 121):
                with self.subTest(scope=scope), self.assertRaisesRegex(ValueError, "scope"):
                    prepare_diagnostics(root, root.parent, scope)

    def test_roots_must_exist_and_be_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regular = root / "regular"
            regular.write_text("fixture", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "directories"):
                prepare_diagnostics(regular, root, "file")
            with self.assertRaisesRegex(ValueError, "directories"):
                prepare_diagnostics(root, regular, "file")
            with self.assertRaises(FileNotFoundError):
                prepare_diagnostics(root, root / "missing", "missing")

    def test_generated_inventory_stays_outside_source_before_and_after_fixture_approval(self) -> None:
        # Synthetic paths/tokens are assembled so the test source is itself clean.
        host_path = "/" + "home/" + "runner/" + "fixture/node_modules/pkg"
        fake_secret = "ghp" + "_" + "A" * 36
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "source"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "README.md").write_text("Synthetic release fixture.", encoding="utf-8")
            diagnostics = prepare_diagnostics(root, base, "synthetic-release")
            report = diagnostics / "node-licenses.json"
            report.write_text(json.dumps({"path": host_path}), encoding="utf-8")
            for with_approval in (False, True):
                with self.subTest(approval_fixture_present=with_approval):
                    if with_approval:
                        approval = root / "release/gate-d-approval.json"
                        approval.parent.mkdir()
                        approval.write_text(
                            json.dumps({"testFixtureOnly": True, "sourceCommitSha": "a" * 40}),
                            encoding="utf-8",
                        )
                    files = _candidate_files(root)
                    self.assertNotIn(report, files)
                    self.assertEqual(_scan_hygiene(root, files), ([], []))

            # The old in-tree placement must STILL be rejected, not ignored.
            legacy = root / "release-scan-artifacts/node-licenses.json"
            legacy.parent.mkdir()
            legacy.write_bytes(report.read_bytes())
            paths, secrets = _scan_hygiene(root, _candidate_files(root))
            self.assertEqual(paths, ["release-scan-artifacts/node-licenses.json"])
            self.assertEqual(secrets, [])

            # Genuine source leakage is rejected whether tracked or untracked.
            leak = root / "unexpected-source.json"
            leak.write_text(json.dumps({"path": host_path, "token": fake_secret}), encoding="utf-8")
            for tracked in (False, True):
                with self.subTest(tracked=tracked):
                    if tracked:
                        subprocess.run(["git", "-C", str(root), "add", leak.name], check=True)
                    paths, secrets = _scan_hygiene(root, _candidate_files(root))
                    self.assertIn(leak.name, paths)
                    self.assertEqual(secrets, [leak.name])

    def test_existing_link_is_rejected_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "source"
            root.mkdir()
            target = base / "target"
            target.mkdir()
            link = base / "plategauge-diagnostics-link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("Native symlink creation is unavailable on this platform")
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare_diagnostics(root, base, "link")
            self.assertEqual(list(target.iterdir()), [])

    def test_resolved_temporary_alias_into_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "source"
            root.mkdir()
            alias = base / "alias"
            try:
                alias.symlink_to(root, target_is_directory=True)
            except OSError:
                self.skipTest("Native symlink creation is unavailable on this platform")
            with self.assertRaisesRegex(ValueError, "outside"):
                prepare_diagnostics(root, alias, "linked")
            self.assertEqual(list(root.iterdir()), [])


class ReleaseRehearsalContractTests(unittest.TestCase):
    def test_release_and_read_only_ci_share_the_same_engineering_action(self) -> None:
        root = Path(__file__).resolve().parents[2]
        release = (root / ".github/workflows/release-pages.yml").read_text(encoding="utf-8")
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        action = (root / ".github/actions/release-checks/action.yml").read_text(encoding="utf-8")
        shared = "uses: ./.github/actions/release-checks"
        self.assertEqual(release.count(shared), 1)
        self.assertEqual(ci.count(shared), 1)
        self.assertLess(action.index("Audit JavaScript dependencies"), action.index("Run Python release checks"))
        self.assertLess(action.index("Build the static release"), action.index("Run Python release checks"))
        self.assertIn('report-path: ${{ env.PG_DIAGNOSTICS_DIR }}/gitleaks.json', action)
        self.assertIn('path: ${{ env.PG_DIAGNOSTICS_DIR }}', action)
        self.assertIn("--temp-root \"$RUNNER_TEMP\"", action)
        self.assertNotIn("release-scan-artifacts/", action)
        self.assertNotIn("hashFiles(", action)
        self.assertIn("pnpm test:production", action)
        self.assertLess(action.index("pnpm test:production"), action.index("Preserve production smoke diagnostics"))
        rehearsal = ci.split("  release-rehearsal:", 1)[1]
        self.assertIn("contents: read", rehearsal)
        self.assertIn("test ! -e release/gate-d-approval.json", rehearsal)
        for forbidden in ("pages: write", "id-token: write", "deploy-pages@", "configure-pages@", "git tag", "git push"):
            self.assertNotIn(forbidden, rehearsal + action)
        # Actual publication still requires the separate committed approval.
        self.assertIn('test "$changed_paths" = "release/gate-d-approval.json"', release)
        self.assertIn("scripts/verify_release_gate.py", release)
        self.assertLess(release.index("scripts/verify_release_gate.py"), release.index("actions/configure-pages@"))


if __name__ == "__main__":
    unittest.main()
