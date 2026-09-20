from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plategauge.errors import DataIntegrityError
from plategauge.web_evidence import (
    build_web_benchmark_evidence,
    verify_web_benchmark_evidence,
)


class WebBenchmarkEvidenceTests(unittest.TestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_checked_in_payload_is_exactly_reproducible(self) -> None:
        report = verify_web_benchmark_evidence(self.repo_root)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["exampleCount"], 10)
        self.assertEqual(report["sourceFileCount"], 18)
        self.assertEqual(
            report["paths"],
            [
                "web/src/generated/benchmarkEvidence.json",
                "web/public/evidence/benchmark-evidence.json",
            ],
        )
        generated = self.repo_root / report["paths"][0]
        downloadable = self.repo_root / report["paths"][1]
        self.assertEqual(generated.read_bytes(), downloadable.read_bytes())

    def test_payload_uses_frozen_populations_and_largest_error_order(self) -> None:
        payload = build_web_benchmark_evidence(self.repo_root)
        metrics = payload["frozenMetrics"]
        examples = payload["benchmarkExamples"]
        self.assertEqual(metrics["validPairs"], 514)
        self.assertEqual(metrics["categories"], 34)
        self.assertEqual(
            [item["id"] for item in examples if item["kind"] == "largest_error"],
            [
                "lefood-0530",
                "lefood-0320",
                "lefood-0226",
                "lefood-0400",
                "lefood-0507",
            ],
        )
        self.assertGreater(metrics["pairedMacroMae"], metrics["afterOnlyMacroMae"])

    def test_exposes_every_workload_with_non_misleading_roles(self) -> None:
        payload = build_web_benchmark_evidence(self.repo_root)
        evidence = payload["workloadEvidence"]
        records = evidence["records"]
        self.assertEqual(evidence["modelAndControlWorkloadCount"], 7)
        self.assertEqual(evidence["contextualReferenceCount"], 1)
        self.assertEqual(len(records), 8)
        self.assertEqual(
            [record["macroCategoryMae"] for record in records],
            sorted(record["macroCategoryMae"] for record in records),
        )
        by_id = {record["id"]: record for record in records}
        self.assertEqual(
            by_id["observer_score_context_only"]["role"], "contextual_reference"
        )
        self.assertIn("not a deployable model", by_id["observer_score_context_only"]["caveat"])
        self.assertEqual(
            by_id["fixed_within_category_wrong_pair"]["role"],
            "destructive_mismatch_control",
        )
        self.assertIn(
            "not evidence that the before image adds predictive value",
            by_id["fixed_within_category_wrong_pair"]["caveat"],
        )
        self.assertEqual(by_id["paired_mobilenet"]["macroCategoryMae"], 0.12275587386595668)
        self.assertEqual(by_id["after_only_mobilenet"]["macroCategoryMae"], 0.09785758682716902)
        self.assertTrue(all(record["count"] == 514 for record in records))
        self.assertTrue(all(record["categoryCount"] == 34 for record in records))

    def test_category_comparisons_are_complete_and_prediction_derived(self) -> None:
        payload = build_web_benchmark_evidence(self.repo_root)
        records = payload["categoryComparisons"]
        self.assertEqual(len(records), 34)
        self.assertEqual([record["category"] for record in records], sorted(record["category"] for record in records))
        self.assertEqual(sum(record["support"] for record in records), 514)
        by_category = {record["category"]: record for record in records}
        self.assertEqual(by_category["001"]["support"], 78)
        self.assertEqual(by_category["002"]["support"], 76)
        for record in records:
            self.assertAlmostEqual(
                record["pairedMae"] - record["afterOnlyMae"],
                record["pairedMinusAfterOnly"],
                places=15,
            )

    def test_endpoint_and_robustness_boundaries_are_explicit(self) -> None:
        payload = build_web_benchmark_evidence(self.repo_root)
        prevalence = payload["endpointPrevalence"]
        self.assertEqual(prevalence["exactZero"], 207)
        self.assertEqual(prevalence["exactOne"], 47)
        self.assertEqual(prevalence["endpointTotal"], 254)
        self.assertEqual(prevalence["interior"], 260)
        self.assertEqual(prevalence["total"], 514)

        robustness = payload["robustnessSummary"]
        self.assertTrue(robustness["downgradeRequired"])
        by_id = {record["id"]: record for record in robustness["records"]}
        after_blur = by_id["after_gaussian_blur_sigma_1"]
        self.assertEqual(after_blur["deltaFromClean"], 0.034532527658502635)
        self.assertEqual(after_blur["downgradeThreshold"], 0.03)
        self.assertTrue(after_blur["thresholdBreached"])
        self.assertEqual(by_id["misuse_same_before_image"]["role"], "misuse_test")
        self.assertEqual(by_id["misuse_swapped_order"]["role"], "misuse_test")
        self.assertEqual(by_id["misuse_unrelated_after"]["role"], "misuse_test")
        self.assertIn("not a held-out generalization estimate", robustness["caveat"])
        self.assertRegex(
            payload["provenance"]["sourceFiles"]["reports/robustness.json"],
            r"^[a-f0-9]{64}$",
        )

    def test_failure_notes_are_the_reviewed_annotations_verbatim(self) -> None:
        payload = build_web_benchmark_evidence(self.repo_root)
        failures = {
            item["id"]: item["note"]
            for item in payload["benchmarkExamples"]
            if item["kind"] == "largest_error"
        }
        with (self.repo_root / "reports/error_review_annotations.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            annotations = {row["sample_id"]: row for row in csv.DictReader(handle)}
        self.assertEqual(
            failures,
            {sample_id: annotations[sample_id]["review_note"] for sample_id in failures},
        )

    def test_edited_generated_payload_is_rejected(self) -> None:
        source = self.repo_root / "web/src/generated/benchmarkEvidence.json"
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "benchmarkEvidence.json"
            payload = json.loads(source.read_text(encoding="utf-8"))
            payload["frozenMetrics"]["pairedMacroMae"] = 0.01
            artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "stale or edited"):
                verify_web_benchmark_evidence(self.repo_root, artifact)

    def test_edited_downloadable_copy_is_rejected(self) -> None:
        public_copy = (
            self.repo_root / "web/public/evidence/benchmark-evidence.json"
        ).resolve()
        original_read_bytes = Path.read_bytes

        def read_with_public_tamper(path: Path) -> bytes:
            if path.resolve() == public_copy:
                return b'{"tampered": true}\n'
            return original_read_bytes(path)

        with (
            patch.object(Path, "read_bytes", read_with_public_tamper),
            self.assertRaisesRegex(DataIntegrityError, "stale or edited"),
        ):
            verify_web_benchmark_evidence(self.repo_root)


if __name__ == "__main__":
    unittest.main()
