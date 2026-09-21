from __future__ import annotations

import csv
import json
import shutil
import tempfile
import tomllib
import unittest
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from plategauge import fold_amendment
from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.fold_amendment import (
    ADVISORY_STATUS,
    PINNED_INPUT_HASHES,
    FrozenInputHashes,
    build_fold_amendment_proposal,
)
from plategauge.folds import FROZEN_CATEGORY_FOLDS, validate_duplicate_groups
from plategauge.orchestration import protocol_preflight
from plategauge.schema import read_manifest
from scripts.propose_fold_amendment import main as proposal_main

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_FILES = (
    Path("data/manifests/lefood_v1_manifest.csv"),
    Path("data/manifests/lefood_v1_duplicate_candidates.csv"),
    Path("data/manifests/lefood_v1_audit.json"),
    Path("configs/frozen_folds.json"),
    Path("reports/data_gate/fold_amendment_candidate.json"),
)
INPUT_FILES = FROZEN_FILES[:-1]
PROTECTED_FILES = (*FROZEN_FILES, Path("reports/data_gate/fold_amendment_applied.json"))

PREREGISTERED_FOLDS = """{
  "schema_version": "1.0",
  "status": "preregistered; duplicate-review gate unresolved",
  "folds": {
    "0": {"categories": ["001", "019", "022", "027", "005"], "expected_n": 103},
    "1": {"categories": ["002", "014", "010", "032", "003"], "expected_n": 103},
    "2": {"categories": ["029", "024", "011", "012", "033", "016", "028", "025"], "expected_n": 103},
    "3": {"categories": ["013", "031", "026", "004", "021", "017", "008", "006"], "expected_n": 103},
    "4": {"categories": ["023", "009", "015", "007", "030", "020", "018", "000"], "expected_n": 102}
  }
}
"""
PREREGISTERED_DUPLICATE_ISSUE = (
    "Duplicate groups cross folds: {'dup-15f25e4070f6': [3, 4], "
    "'dup-84e0fa596bc4': [2, 4], 'dup-faf29cbb02fd': [2, 4], "
    "'dup-c7a1ff728d7c': [3, 4], 'dup-d06da4f9b06c': [3, 4], "
    "'dup-c67b65330d5d': [0, 1]}"
)


def restore_preregistered_inputs(root: Path) -> None:
    candidate = json.loads(
        (REPO_ROOT / "reports/data_gate/fold_amendment_candidate.json").read_text(encoding="utf-8")
    )
    original_assignment = {
        category: fold
        for fold in range(5)
        for category in candidate["candidate_folds"][str(fold)]["categories"]
    }
    for moved in candidate["moved_categories"]:
        original_assignment[moved["category"]] = moved["from_fold"]

    manifest_path = root / INPUT_FILES[0]
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if fieldnames is None:
        raise AssertionError("Fixture manifest has no header")
    for row in rows:
        row["outer_fold"] = str(original_assignment[row["category"]])
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    (root / INPUT_FILES[3]).write_bytes((PREREGISTERED_FOLDS + "\n").encode())
    audit_path = root / INPUT_FILES[2]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.pop("manifest_sha256")
    audit["cross_fold_duplicate_components"] = 6
    audit["issues"] = [PREREGISTERED_DUPLICATE_ISSUE]
    audit["passed"] = False
    # The historical audit was hashed as CRLF. Reconstruct those exact bytes on
    # every host; the pinned hashes and frozen evidence are not rewritten.
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\r\n",
    )


def prepare_historical_repo(root: Path) -> None:
    for relative in INPUT_FILES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)
    restore_preregistered_inputs(root)
    actual_hashes = hashes_for(root)
    if actual_hashes != PINNED_INPUT_HASHES:
        raise AssertionError(
            "Historical proposal fixture does not reproduce the pinned input hashes: "
            f"{actual_hashes!r}"
        )


@contextmanager
def copied_input_repo() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        prepare_historical_repo(root)
        yield root


def hashes_for(root: Path) -> FrozenInputHashes:
    return FrozenInputHashes(
        manifest=sha256_file(root / INPUT_FILES[0]),
        duplicate_candidates=sha256_file(root / INPUT_FILES[1]),
        audit_report=sha256_file(root / INPUT_FILES[2]),
        frozen_folds=sha256_file(root / INPUT_FILES[3]),
    )


def rewrite_json(path: Path, mutate: Callable[[object], object]) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(mutate(document), indent=2) + "\n", encoding="utf-8")


class FoldAmendmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before_hashes = {path: sha256_file(REPO_ROOT / path) for path in PROTECTED_FILES}
        cls.historical_directory = tempfile.TemporaryDirectory()
        cls.historical_root = Path(cls.historical_directory.name)
        prepare_historical_repo(cls.historical_root)
        cls.proposal = build_fold_amendment_proposal(cls.historical_root)

    @classmethod
    def tearDownClass(cls) -> None:
        after_hashes = {path: sha256_file(REPO_ROOT / path) for path in PROTECTED_FILES}
        cls.historical_directory.cleanup()
        if after_hashes != cls.before_hashes:
            raise AssertionError("Read-only fold proposal changed a frozen input or advisory")

    def test_reproduces_checked_in_advisory_exactly(self) -> None:
        expected = json.loads(
            (REPO_ROOT / "reports/data_gate/fold_amendment_candidate.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(self.proposal, expected)
        self.assertEqual(self.proposal["status"], ADVISORY_STATUS)
        self.assertFalse(self.proposal["binding"])
        self.assertEqual(
            self.proposal["optimization"],
            {
                "method": (
                    "deterministic exhaustive dynamic programming over connected category "
                    "components and remaining fold capacities"
                ),
                "objective_order": [
                    "minimize number of records moved from the preregistered fold assignment",
                    "then minimize number of categories moved",
                ],
                "states_evaluated": 5_113_609,
                "memoized_state_hits": 8_346_050,
                "optimal_moved_records": 90,
                "optimal_moved_categories": 8,
            },
        )

    def test_candidate_is_exact_and_duplicate_components_are_atomic(self) -> None:
        folds = self.proposal["candidate_folds"]
        self.assertEqual([folds[str(index)]["n"] for index in range(5)], [103, 103, 103, 103, 102])
        category_fold = {
            category: fold for fold in range(5) for category in folds[str(fold)]["categories"]
        }
        self.assertEqual(len(category_fold), 34)
        for component in self.proposal["duplicate_induced_category_components"]:
            self.assertEqual(len({category_fold[category] for category in component}), 1)

    def test_approved_candidate_is_the_active_verified_split(self) -> None:
        candidate = json.loads(
            (REPO_ROOT / "reports/data_gate/fold_amendment_candidate.json").read_text(
                encoding="utf-8"
            )
        )
        configuration = json.loads(
            (REPO_ROOT / "configs/frozen_folds.json").read_text(encoding="utf-8")
        )
        applied = json.loads(
            (REPO_ROOT / "reports/data_gate/fold_amendment_applied.json").read_text(
                encoding="utf-8"
            )
        )
        audit = json.loads(
            (REPO_ROOT / "data/manifests/lefood_v1_audit.json").read_text(encoding="utf-8")
        )
        experiment = tomllib.loads(
            (REPO_ROOT / "configs/experiment.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(configuration["schema_version"], "1.0")
        self.assertEqual(configuration["status"], "approved; duplicate-safe amendment active")
        self.assertEqual(
            configuration["amendment"]["source_sha256"], sha256_file(REPO_ROOT / FROZEN_FILES[4])
        )
        self.assertEqual(applied["status"], "ACTIVE_APPROVED")

        configured_folds = {
            int(fold): tuple(entry["categories"]) for fold, entry in configuration["folds"].items()
        }
        candidate_folds = {
            int(fold): tuple(entry["categories"])
            for fold, entry in candidate["candidate_folds"].items()
        }
        self.assertEqual(configured_folds, candidate_folds)
        self.assertEqual(configured_folds, FROZEN_CATEGORY_FOLDS)

        records = read_manifest(REPO_ROOT / INPUT_FILES[0])
        valid = [record for record in records if record.is_valid]
        self.assertEqual(len(records), 524)
        self.assertEqual(len(valid), 514)
        self.assertEqual(
            dict(sorted(Counter(record.outer_fold for record in valid).items())),
            {0: 103, 1: 103, 2: 103, 3: 103, 4: 102},
        )
        category_folds: dict[str, set[int]] = defaultdict(set)
        duplicate_folds: dict[str, set[int]] = defaultdict(set)
        for record in records:
            category_folds[record.category].add(record.outer_fold)
            if record.is_valid:
                for group in record.duplicate_group.split("+"):
                    if group:
                        duplicate_folds[group].add(record.outer_fold)
        self.assertEqual(len(category_folds), 34)
        self.assertTrue(all(len(folds) == 1 for folds in category_folds.values()))
        self.assertEqual(len(duplicate_folds), 9)
        self.assertTrue(all(len(folds) == 1 for folds in duplicate_folds.values()))
        validate_duplicate_groups(
            (record.category for record in valid),
            (record.duplicate_group for record in valid),
            (record.outer_fold for record in valid),
        )
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["issues"], [])
        self.assertEqual(audit["cross_fold_duplicate_components"], 0)

        after_paths = {
            "frozen_folds_sha256": Path("configs/frozen_folds.json"),
            "experiment_config_sha256": Path("configs/experiment.toml"),
            "folds_code_sha256": Path("src/plategauge/folds.py"),
            "manifest_sha256": INPUT_FILES[0],
            "duplicate_candidates_sha256": INPUT_FILES[1],
            "source_audit_sha256": Path("data/manifests/lefood_v1_source_audit.csv"),
            "audit_report_sha256": INPUT_FILES[2],
        }
        self.assertEqual(
            applied["after"],
            {key: sha256_file(REPO_ROOT / path) for key, path in after_paths.items()},
        )
        self.assertEqual(applied["verification"]["fold_sizes"], [103, 103, 103, 103, 102])
        self.assertEqual(applied["verification"]["cross_fold_duplicate_components"], 0)
        self.assertEqual(applied["verification"]["protocol_status"], experiment["protocol_status"])
        preflight, protocol = protocol_preflight(
            audit_report_path=REPO_ROOT / INPUT_FILES[2],
            manifest_path=REPO_ROOT / INPUT_FILES[0],
            config_path=REPO_ROOT / "configs/experiment.toml",
            folds_path=REPO_ROOT / "configs/frozen_folds.json",
        )
        self.assertEqual(preflight.status, "ready", preflight.blockers)
        self.assertIsNotNone(protocol)
        moved_categories = {item["category"] for item in candidate["moved_categories"]}
        observed_change = {
            "moved_valid_records": sum(
                record.is_valid and record.category in moved_categories for record in records
            ),
            "moved_excluded_records": sum(
                not record.is_valid and record.category in moved_categories for record in records
            ),
            "manifest_rows_reassigned": sum(
                record.category in moved_categories for record in records
            ),
            "moved_categories": len(moved_categories),
        }
        self.assertEqual(applied["approved_change"], observed_change)

        def csv_by_id(path: Path) -> dict[str, dict[str, str]]:
            with path.open("r", encoding="utf-8", newline="") as handle:
                return {row["sample_id"]: row for row in csv.DictReader(handle)}

        before_rows = csv_by_id(self.historical_root / INPUT_FILES[0])
        after_rows = csv_by_id(REPO_ROOT / INPUT_FILES[0])
        self.assertEqual(set(before_rows), set(after_rows))
        changed_rows: list[dict[str, str]] = []
        for sample_id, before_row in before_rows.items():
            after_row = after_rows[sample_id]
            self.assertEqual(
                {key: value for key, value in before_row.items() if key != "outer_fold"},
                {key: value for key, value in after_row.items() if key != "outer_fold"},
            )
            if before_row["outer_fold"] != after_row["outer_fold"]:
                changed_rows.append(after_row)
        observed_integrity = {
            "rows_compared": len(after_rows),
            "non_outer_fold_fields_unchanged": True,
            "outer_fold_rows_changed": len(changed_rows),
            "valid_rows_changed": sum(row["is_valid"] == "true" for row in changed_rows),
            "excluded_rows_changed": sum(row["is_valid"] == "false" for row in changed_rows),
            "changed_categories": sorted({row["category"] for row in changed_rows}),
        }
        self.assertEqual(applied["manifest_integrity"], observed_integrity)

    def test_changed_input_fails_closed_even_when_rehashed(self) -> None:
        with copied_input_repo() as root:
            duplicates = root / "data/manifests/lefood_v1_duplicate_candidates.csv"
            text = duplicates.read_text(encoding="utf-8")
            duplicates.write_text(text.replace("0.9956140326", "0.1000000000", 1), encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "SSIM gate"):
                build_fold_amendment_proposal(root, expected_hashes=hashes_for(root))

    def test_default_hash_pin_rejects_tampering_before_optimization(self) -> None:
        with copied_input_repo() as root:
            manifest = root / "data/manifests/lefood_v1_manifest.csv"
            manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "Manifest SHA-256 differs"):
                build_fold_amendment_proposal(root)

    def assert_mutation_rejected(
        self,
        relative: str,
        mutate: Callable[[Path], None],
        message: str,
    ) -> None:
        with copied_input_repo() as root:
            mutate(root / relative)
            with self.assertRaisesRegex(DataIntegrityError, message):
                build_fold_amendment_proposal(root, expected_hashes=hashes_for(root))

    def test_frozen_fold_schema_drift_fails_closed(self) -> None:
        relative = "configs/frozen_folds.json"

        def invalid_json(path: Path) -> None:
            path.write_text("{", encoding="utf-8")

        def non_object(path: Path) -> None:
            path.write_text("[]\n", encoding="utf-8")

        def changed_status(path: Path) -> None:
            def mutate(value: object) -> object:
                assert isinstance(value, dict)
                value["status"] = "approved"
                return value

            rewrite_json(path, mutate)

        def boolean_capacity(path: Path) -> None:
            def mutate(value: object) -> object:
                assert isinstance(value, dict)
                value["folds"]["0"]["expected_n"] = True
                return value

            rewrite_json(path, mutate)

        def duplicate_category(path: Path) -> None:
            def mutate(value: object) -> object:
                assert isinstance(value, dict)
                value["folds"]["1"]["categories"].append("001")
                return value

            rewrite_json(path, mutate)

        cases = (
            (invalid_json, "not valid UTF-8 JSON"),
            (non_object, "must be a JSON object"),
            (changed_status, "status no longer describes"),
            (boolean_capacity, "expected_n must be an integer"),
            (duplicate_category, "occurs in multiple frozen folds"),
        )
        for mutate, message in cases:
            with self.subTest(message=message):
                self.assert_mutation_rejected(relative, mutate, message)

    def test_duplicate_review_schema_and_evidence_fail_closed(self) -> None:
        relative = "data/manifests/lefood_v1_duplicate_candidates.csv"

        def replace_once(old: str, new: str) -> Callable[[Path], None]:
            def mutate(path: Path) -> None:
                text = path.read_text(encoding="utf-8")
                self.assertIn(old, text)
                path.write_text(text.replace(old, new, 1), encoding="utf-8")

            return mutate

        def empty_review(path: Path) -> None:
            header = path.read_text(encoding="utf-8").splitlines()[0]
            path.write_text(header + "\n", encoding="utf-8")

        def invalid_utf8(path: Path) -> None:
            path.write_bytes(b"\xff\xfe")

        def extra_row_field(path: Path) -> None:
            lines = path.read_text(encoding="utf-8").splitlines()
            lines[1] += ",unexpected"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        def omit_one_group(path: Path) -> None:
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join((lines[0], *lines[2:])) + "\n", encoding="utf-8")

        cases = (
            (replace_once("left_path", "left"), "columns differ"),
            (empty_review, "must not be empty"),
            (invalid_utf8, "cannot be read as UTF-8 CSV"),
            (extra_row_field, "row 2 fields changed"),
            (replace_once("phash_ssim", "manual_review"), "unknown match_type"),
            (replace_once(",4,0.9956140326,", ",not-an-int,0.9956140326,"), "non-numeric"),
            (replace_once(",4,0.9956140326,", ",5,0.9956140326,"), "pHash gate"),
            (
                replace_once("phash_ssim,4,0.9956140326", "exact_sha256,4,0.9956140326"),
                "invalid exact metrics",
            ),
            (
                replace_once(
                    "leftover dataset/data_after/004/004_166_DSC_0103_aft.JPG", "missing.JPG"
                ),
                "exactly one valid manifest record",
            ),
            (
                replace_once("dup-15f25e4070f6", "dup-not-in-manifest"),
                "is absent from manifest record",
            ),
            (omit_one_group, "identifiers differ"),
        )
        for mutate, message in cases:
            with self.subTest(message=message):
                self.assert_mutation_rejected(relative, mutate, message)

    def test_audit_inconsistency_fails_closed(self) -> None:
        relative = "data/manifests/lefood_v1_audit.json"

        def add_field(path: Path) -> None:
            def mutate(value: object) -> object:
                assert isinstance(value, dict)
                value["unexpected"] = True
                return value

            rewrite_json(path, mutate)

        def wrong_count(path: Path) -> None:
            def mutate(value: object) -> object:
                assert isinstance(value, dict)
                value["valid_pairs"] = 513
                return value

            rewrite_json(path, mutate)

        def no_issues(path: Path) -> None:
            def mutate(value: object) -> object:
                assert isinstance(value, dict)
                value["issues"] = []
                return value

            rewrite_json(path, mutate)

        cases = (
            (add_field, "fields differ"),
            (wrong_count, "valid_pairs.*inconsistent"),
            (no_issues, "non-empty string issue list"),
        )
        for mutate, message in cases:
            with self.subTest(message=message):
                self.assert_mutation_rejected(relative, mutate, message)

    def test_missing_or_short_manifest_fails_closed(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(DataIntegrityError, "not a regular file"),
        ):
            build_fold_amendment_proposal(directory)

        def remove_record(path: Path) -> None:
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

        self.assert_mutation_rejected(
            "data/manifests/lefood_v1_manifest.csv",
            remove_record,
            "must contain 524 matched pairs",
        )

    def test_optimizer_fails_closed_when_exact_capacities_are_impossible(self) -> None:
        oversized = fold_amendment._Component(
            categories=("synthetic",),
            size=104,
            moved_records=(0, 0, 0, 0, 0),
            moved_categories=(0, 0, 0, 0, 0),
        )
        with self.assertRaisesRegex(DataIntegrityError, "No exact-capacity"):
            fold_amendment._solve([oversized])
        with self.assertRaisesRegex(DataIntegrityError, "one exact-capacity optimum"):
            fold_amendment._solve([])

    def test_cli_stdout_is_json_and_status_is_explicit_without_writes(self) -> None:
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = proposal_main(["--repo-root", str(self.historical_root)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stdout.getvalue()), self.proposal)
        self.assertEqual(
            stderr.getvalue(),
            "NOT_ACTIVE_REQUIRES_APPROVAL: advisory printed; frozen inputs and active folds "
            "were not changed.\n",
        )

    def test_cli_failure_has_no_partial_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "not-a-repository"
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = proposal_main(["--repo-root", str(missing)])
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("BLOCKED: Repository root must be a real directory", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
