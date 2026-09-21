"""Network-free monitoring regressions; no models, datasets or fitting."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.monitor_documentation import (
    classify_report,
    prepare_inputs,
    summarize,
    tracked_markdown,
)


def fixture_report(code: int | None = None, *, timeout: bool = False) -> dict:
    report = {
        "total": 1,
        "successful": 1,
        "unknown": 0,
        "unsupported": 0,
        "timeouts": 0,
        "excludes": 0,
        "errors": 0,
        "cached": 0,
        "error_map": {},
        "timeout_map": {},
    }
    if code is not None or timeout:
        field, count = ("timeout_map", "timeouts") if timeout else ("error_map", "errors")
        report["successful"] = 0
        report[count] = 1
        report[field] = {
            "README.md": [
                {
                    "url": "https://example.invalid/reference",
                    "status": {
                        "text": "Synthetic timeout" if timeout else "Synthetic HTTP response",
                        "code": code,
                    },
                }
            ]
        }
    return report


class TrackedScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        self.output = self.base / "diagnostics"
        self.output.mkdir()

    def add(
        self, name: str, *, tracked: bool = True, text: str = "# Synthetic documentation\n"
    ) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if tracked:
            subprocess.run(
                ["git", "-C", str(self.root), "add", "--", name], check=True, capture_output=True
            )

    def test_only_tracked_project_markdown_and_explicit_dependency_exclusions(self) -> None:
        for name in ("README.md", "docs/guide with spaces.md", "-options.md"):
            self.add(name)
        for name in ("web/node_modules/pkg/README.md", "web/dist/notes.md", ".venv/guide.md"):
            self.add(name)
        self.add("notes/private.md", tracked=False)
        self.add("README.txt")
        result = prepare_inputs(self.root, self.output)
        names = [item["path"] for item in result["files"]]
        self.assertEqual(names, ["-options.md", "README.md", "docs/guide with spaces.md"])
        self.assertEqual(len(result["excludedTrackedPaths"]), 3)
        self.assertEqual(
            (self.output / "inputs.txt").read_bytes(),
            b"./-options.md\n./README.md\n./docs/guide with spaces.md\n",
        )
        self.assertTrue(all(len(item["sha256"]) == 64 for item in result["files"]))

    def test_nonempty_scan_and_no_untracked_fallback(self) -> None:
        self.add("README.md", tracked=False)
        with self.assertRaisesRegex(ValueError, "No tracked"):
            tracked_markdown(self.root)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_stale_diagnostics_are_not_overwritten(self) -> None:
        self.add("README.md")
        prepare_inputs(self.root, self.output)
        original = (self.output / "inputs.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "empty"):
            prepare_inputs(self.root, self.output)
        self.assertEqual(original, (self.output / "inputs.json").read_bytes())

    def test_in_tree_and_ancestor_outputs_are_rejected(self) -> None:
        self.add("README.md")
        for path in (self.root, self.base):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "outside"):
                prepare_inputs(self.root, path)

    def test_missing_tracked_file_fails(self) -> None:
        self.add("README.md")
        (self.root / "README.md").unlink()
        with self.assertRaises(FileNotFoundError):
            tracked_markdown(self.root)

    def test_git_failure_is_not_empty_success(self) -> None:
        with (
            patch(
                "scripts.monitor_documentation.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "git"),
            ),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            tracked_markdown(self.root)

    def test_unsafe_file_list_syntax_is_rejected_before_access(self) -> None:
        for name in (
            "../escape.md",
            "/absolute.md",
            "docs/*.md",
            "docs/[x].md",
            "docs/a\nb.md",
            "docs/a\rb.md",
            "https://example.invalid/a.md",
            "docs/$(whoami).md",
            "docs/'quote.md",
            "#comment.md",
        ):
            with (
                self.subTest(name=name),
                patch("scripts.monitor_documentation.subprocess.run") as run,
            ):
                run.return_value.stdout = name.encode() + b"\0"
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    tracked_markdown(self.root)

    def test_symlink_input_rejected_without_reading_target(self) -> None:
        self.add("README.md")
        with (
            patch.object(Path, "is_symlink", return_value=True),
            self.assertRaisesRegex(ValueError, "Symlink"),
        ):
            tracked_markdown(self.root)

    def test_cli_prepare_and_failure_exit_codes(self) -> None:
        self.add("README.md")
        script = Path(__file__).resolve().parents[2] / "scripts/monitor_documentation.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "prepare",
                "--repo-root",
                str(self.root),
                "--output-dir",
                str(self.output),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "summarize",
                "--report",
                str(self.output / "missing.json"),
                "--output-dir",
                str(self.output),
                "--checker-exit",
                "",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "checker_error")


class ReportTests(unittest.TestCase):
    def test_success_requires_successful_nonempty_check(self) -> None:
        self.assertEqual(classify_report(fixture_report(), 0)["status"], "passed")
        for changes, exit_code in (
            ({"total": 0, "successful": 0}, 0),
            ({}, 1),
            ({"successful": 0, "excludes": 1}, 0),
        ):
            report = fixture_report()
            report.update(changes)
            with self.subTest(changes=changes, exit_code=exit_code):
                self.assertEqual(classify_report(report, exit_code)["status"], "failed")

    def test_within_run_duplicate_reuse_is_not_a_failure(self) -> None:
        report = fixture_report()
        report.update({"total": 2, "successful": 2, "cached": 1})
        result = classify_report(report, 0)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["counts"]["cached"], 1)
        self.assertTrue(result["cachedCountMayIncludeWithinRunDeduplication"])

    def test_http_failures_are_classified_not_accepted(self) -> None:
        for code, expected in (
            (401, "blocked_or_rate_limited"),
            (403, "blocked_or_rate_limited"),
            (429, "blocked_or_rate_limited"),
            (404, "broken_reference"),
            (410, "broken_reference"),
            (500, "upstream_error"),
            (503, "upstream_error"),
            (301, "other_error"),
        ):
            with self.subTest(code=code):
                result = classify_report(fixture_report(code), 0)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["classifications"], {expected: 1})
                self.assertEqual(result["findings"][0]["status"]["code"], code)

    def test_timeouts_and_transport_errors_fail(self) -> None:
        self.assertEqual(
            classify_report(fixture_report(timeout=True), 2)["classifications"], {"timeout": 1}
        )
        report = fixture_report(500)
        del report["error_map"]["README.md"][0]["status"]["code"]
        self.assertEqual(classify_report(report, 2)["classifications"], {"other_error": 1})

    def test_unknown_and_unsupported_do_not_pass(self) -> None:
        for category in ("unknown", "unsupported"):
            report = fixture_report()
            report.update({"successful": 0, category: 1})
            self.assertEqual(classify_report(report, 0)["status"], "failed")

    def test_invalid_counters_and_totals_fail_closed(self) -> None:
        for value in (-1, True, "1", None):
            report = fixture_report()
            report["total"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                classify_report(report, 0)
        report = fixture_report()
        report["total"] = 4
        with self.assertRaisesRegex(ValueError, "totals"):
            classify_report(report, 0)

    def test_malformed_maps_and_findings_fail_closed(self) -> None:
        variants = [
            None,
            [],
            {"README.md": 1},
            {2: []},
            {"README.md": [None]},
            {"README.md": [{"url": 123}]},
            {"README.md": [{"url": "x", "status": None}]},
        ]
        for value in variants:
            report = fixture_report(403)
            report["error_map"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                classify_report(report, 2)
        for code in (True, "403", 0, 700):
            report = fixture_report(403)
            report["error_map"]["README.md"][0]["status"]["code"] = code
            with self.subTest(code=code), self.assertRaises(ValueError):
                classify_report(report, 2)
        with self.assertRaises(ValueError):
            classify_report([], 0)

    def test_inconsistent_findings_rejected_and_input_not_mutated(self) -> None:
        report = fixture_report(403)
        original = copy.deepcopy(report)
        classify_report(report, 2)
        self.assertEqual(report, original)
        report["error_map"] = {}
        with self.assertRaisesRegex(ValueError, "Counters"):
            classify_report(report, 2)

    def test_missing_malformed_and_empty_reports_are_recorded(self) -> None:
        for content in (None, "", "not json", "[]", "{}"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report = root / "raw.json"
                if content is not None:
                    report.write_text(content, encoding="utf-8")
                result = summarize(report, root, "")
                self.assertEqual(result["status"], "checker_error")
                self.assertTrue((root / "classification.json").exists())
                with self.assertRaisesRegex(ValueError, "already exists"):
                    summarize(report, root, "")

    def test_valid_report_is_preserved_and_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "raw.json"
            report.write_text(json.dumps(fixture_report()), encoding="utf-8-sig")
            before = report.read_bytes()
            self.assertEqual(summarize(report, root, "0")["status"], "passed")
            self.assertEqual(report.read_bytes(), before)


class WorkflowContractTests(unittest.TestCase):
    def test_monitoring_jobs_are_independent_bounded_and_fail_closed(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/weekly-smoke.yml").read_text()
        live, docs = workflow.split("  documentation-links:", 1)
        self.assertIn("ref: refs/tags/v1.0.2", live)
        self.assertNotIn("needs:", docs)
        self.assertNotIn("pnpm", docs)
        self.assertNotIn("ref: refs/tags", docs)
        self.assertIn("--files-from", docs)
        self.assertIn("format: json", docs)
        self.assertIn("lycheeVersion: v0.24.2", docs)
        self.assertIn("--cache=false --accept 200 --timeout 15", docs)
        self.assertIn("fail: true", docs)
        self.assertIn("always()", docs)
        self.assertIn("timeout-minutes: 5", docs)
        self.assertIn("retention-days: 90", docs)
        for bad in (
            "./**/*.md",
            "continue-on-error",
            "fail: false",
            "--accept-timeouts",
            "200,429",
            "--insecure",
            "--exclude ",
            "pages: write",
            "id-token: write",
            "deploy-pages@",
        ):
            self.assertNotIn(bad, workflow)
        self.assertEqual(live.count("curl "), live.count("--connect-timeout 10 --max-time 60"))

    def test_new_regressions_are_in_regular_cross_platform_ci(self) -> None:
        root = Path(__file__).resolve().parents[2]
        ci = (root / ".github/workflows/ci.yml").read_text()
        synthetic = ci.split("  monitoring-tests:", 1)[1].split("  python:", 1)[0]
        self.assertIn("[ubuntu-latest, windows-latest]", synthetic)
        self.assertIn("test_monitor_documentation.py", synthetic)
        # Installing the runtime manager is allowed; project dependencies are not.
        self.assert_runtime_contract(synthetic)

    def assert_runtime_contract(self, synthetic: str) -> None:
        bootstrap = "python-version: ${{ matrix.os == 'windows-latest' && '3.12.10' || '3.12.14' }}"
        install = (
            "          set -euo pipefail\n"
            "          python -m pip install --disable-pip-version-check uv==0.12.17\n"
            "          uv python install 3.12.14\n"
        )
        runtime = "uv run --no-project --no-config --offline --python 3.12.14 --managed-python"
        verify = (
            runtime
            + '\n          python -c "import sys; assert sys.version_info[:3] == (3, 12, 14)"'
        )
        tests = (
            runtime + "\n          python -m unittest discover -s tests/python "
            "-p test_monitor_documentation.py -v"
        )
        for required in (bootstrap, install, verify, tests, "timeout-minutes: 5"):
            self.assertIn(required, synthetic)
        self.assertLess(synthetic.index(bootstrap), synthetic.index(install))
        self.assertLess(synthetic.index(install), synthetic.index(verify))
        self.assertLess(synthetic.index(verify), synthetic.index(tests))
        self.assertEqual(synthetic.count("shell: bash"), 3)
        self.assertEqual(synthetic.count("pip install"), 1)
        for forbidden in (
            "uv sync",
            "uv pip",
            "--with ",
            "--with-requirements",
            "--all-extras",
            "continue-on-error",
            "|| true",
        ):
            self.assertNotIn(forbidden, synthetic)

    def test_runtime_contract_rejects_the_previous_windows_setup(self) -> None:
        # Reproduce the failed job's setup, not a failure in the monitoring code.
        previous = """    name: Synthetic monitoring tests (${{ matrix.os }})
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    timeout-minutes: 5
    steps:
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: "3.12.14"
      - name: Test scope, failure classification and workflow boundaries without network
        run: python -m unittest discover -s tests/python -p test_monitor_documentation.py -v
"""
        with self.assertRaises(AssertionError):
            self.assert_runtime_contract(previous)

    def test_runtime_contract_rejects_bypass_and_dependency_installation(self) -> None:
        root = Path(__file__).resolve().parents[2]
        ci = (root / ".github/workflows/ci.yml").read_text()
        synthetic = ci.split("  monitoring-tests:", 1)[1].split("  python:", 1)[0]
        self.assert_runtime_contract(synthetic)
        replacements = (
            ("'3.12.10'", "'3.12.14'"),
            ("uv==0.12.17", "uv"),
            ("uv python install 3.12.14", "echo skipped runtime installation"),
            ("--no-project ", ""),
            ("--no-config ", ""),
            ("--offline ", ""),
            ("--managed-python", ""),
            ("assert sys.version_info[:3] == (3, 12, 14)", "print(sys.version)"),
            ("set -euo pipefail", "set +e"),
            ("timeout-minutes: 5", "timeout-minutes: 60"),
        )
        for original, replacement in replacements:
            with self.subTest(bypass=original), self.assertRaises(AssertionError):
                self.assert_runtime_contract(synthetic.replace(original, replacement))
        for extra in (
            "uv sync --all-extras",
            "uv pip install plategauge",
            "continue-on-error: true",
        ):
            with self.subTest(extra=extra), self.assertRaises(AssertionError):
                self.assert_runtime_contract(synthetic + "\n        " + extra + "\n")


if __name__ == "__main__":
    unittest.main()
