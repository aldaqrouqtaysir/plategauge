from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.gate_c_figures import (
    FIGURE_FILENAMES,
    ROUTINE_CONDITION_ORDER,
    TARGET_SLICE_ORDER,
    WORKLOAD_LABELS,
    generate_gate_c_figures,
)
from plategauge.release_artifacts import canonical_json_sha256


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class GateCFigureTests(unittest.TestCase):
    def _reports(self, root: Path) -> tuple[Path, Path, Path]:
        run_id = "1" * 64
        protocol_id = "2" * 64
        manifest_sha256 = "3" * 64
        run_path = root / "run.json"
        _write_json(
            run_path,
            {"run_id": run_id, "protocol": {"protocol_id": protocol_id}},
        )
        run_sha256 = sha256_file(run_path)

        categories = {
            f"{index:03d}": {
                "n": 1,
                "macro_category_mae": 0.01 + index * 0.001,
            }
            for index in range(34)
        }
        after_categories = {
            key: {"n": value["n"], "macro_category_mae": value["macro_category_mae"] + 0.01}
            for key, value in categories.items()
        }
        workloads: dict[str, object] = {}
        for index, key in enumerate(WORKLOAD_LABELS):
            workloads[key] = {
                "overall": {
                    "category_count": 34,
                    "n": 514,
                    "macro_category_mae": 0.05 + index * 0.01,
                }
            }
        paired = dict(workloads["paired_mobilenet"])  # type: ignore[arg-type]
        paired["per_category"] = categories
        paired["slices"] = {
            "target_range": {
                key: {"n": count, "micro_mae": 0.04 + index * 0.03}
                for index, ((key, _), count) in enumerate(
                    zip(TARGET_SLICE_ORDER, (100, 90, 80, 70, 60, 114), strict=True)
                )
            }
        }
        workloads["paired_mobilenet"] = paired
        after = dict(workloads["after_only_mobilenet"])  # type: ignore[arg-type]
        after["per_category"] = after_categories
        workloads["after_only_mobilenet"] = after
        results = {
            "schemaVersion": 1,
            "frozen": True,
            "run_id": run_id,
            "protocol_id": protocol_id,
            "manifest_sha256": manifest_sha256,
            "provenance": {"run_descriptor_sha256": run_sha256},
            "dataset": {"valid_pairs": 514, "categories": 34},
            "decisions": {"numeric_demo": {"worst_broad_target_slice_micro_mae": 0.19}},
            "workloads": workloads,
        }
        results_path = root / "results.json"
        _write_json(results_path, results)

        clean = 0.10
        conditions: list[dict[str, object]] = [
            {
                "name": "clean",
                "group": "clean",
                "macro_category_mae": clean,
                "delta_macro_category_mae_from_clean": 0.0,
            }
        ]
        for index, (name, _) in enumerate(ROUTINE_CONDITION_ORDER):
            delta = -0.005 + index * 0.003
            conditions.append(
                {
                    "name": name,
                    "group": "routine_perturbation",
                    "macro_category_mae": clean + delta,
                    "delta_macro_category_mae_from_clean": delta,
                    "routine_downgrade_threshold": 0.03,
                    "exceeds_routine_downgrade_threshold": delta > 0.03,
                }
            )
        robustness_core = {
            "schema_version": "1.0",
            "status": "complete",
            "kind": "frozen_final_model_robustness",
            "clean_macro_category_mae": clean,
            "conditions": conditions,
            "robustness_downgrade_required": True,
            "dataset_verification": {"manifest_sha256": manifest_sha256},
            "model_identity": {
                "run_id": run_id,
                "protocol_id": protocol_id,
                "hashes": {
                    "manifest_sha256": manifest_sha256,
                    "run_descriptor_sha256": run_sha256,
                },
            },
        }
        robustness_path = root / "robustness.json"
        _write_json(
            robustness_path,
            robustness_core | {"evidence_sha256": canonical_json_sha256(robustness_core)},
        )
        return results_path, robustness_path, run_path

    def test_generates_four_accessible_exact_and_idempotent_svgs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results, robustness, run = self._reports(root)
            output = root / "figures"
            source_hashes = (sha256_file(results), sha256_file(robustness), sha256_file(run))
            paths = generate_gate_c_figures(
                results_path=results,
                robustness_path=robustness,
                run_descriptor_path=run,
                output_directory=output,
            )
            self.assertEqual({path.name for path in paths}, set(FIGURE_FILENAMES.values()))
            first_hashes = {path.name: sha256_file(path) for path in paths}
            for path in paths:
                svg = path.read_text(encoding="utf-8")
                self.assertIn('role="img"', svg)
                self.assertIn("<title id=", svg)
                self.assertIn("<desc id=", svg)
                self.assertIn("<metadata id=", svg)
                self.assertIn('"results_sha256"', svg.replace("&quot;", '"'))
            workload = (output / FIGURE_FILENAMES["workload_macro_mae"]).read_text(encoding="utf-8")
            self.assertIn('data-workload="paired_mobilenet"', workload)
            self.assertIn('data-value="0.10000000000000001"', workload)
            scatter = (output / FIGURE_FILENAMES["category_scatter"]).read_text(encoding="utf-8")
            self.assertEqual(scatter.count('data-category="'), 34)
            self.assertIn("Equal-error line y=x", scatter)
            slices = (output / FIGURE_FILENAMES["target_slices"]).read_text(encoding="utf-8")
            self.assertIn("public gate 0.15", slices)
            robustness_svg = (output / FIGURE_FILENAMES["robustness_delta"]).read_text(
                encoding="utf-8"
            )
            self.assertIn("downgrade line +0.03", robustness_svg)

            resumed = generate_gate_c_figures(
                results_path=results,
                robustness_path=robustness,
                run_descriptor_path=run,
                output_directory=output,
            )
            self.assertEqual(first_hashes, {path.name: sha256_file(path) for path in resumed})
            self.assertEqual(
                source_hashes,
                (sha256_file(results), sha256_file(robustness), sha256_file(run)),
            )

    def test_refuses_divergent_existing_figure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results, robustness, run = self._reports(root)
            output = root / "figures"
            output.mkdir()
            first = output / FIGURE_FILENAMES["workload_macro_mae"]
            first.write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "divergent"):
                generate_gate_c_figures(
                    results_path=results,
                    robustness_path=robustness,
                    run_descriptor_path=run,
                    output_directory=output,
                )
            self.assertEqual(first.read_text(encoding="utf-8"), "tampered\n")

    def test_rejects_tampered_evidence_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results, robustness, run = self._reports(root)
            payload = json.loads(robustness.read_text(encoding="utf-8"))
            payload["conditions"][1]["macro_category_mae"] += 0.001
            _write_json(robustness, payload)
            output = root / "figures"
            with self.assertRaisesRegex(DataIntegrityError, "evidence hash"):
                generate_gate_c_figures(
                    results_path=results,
                    robustness_path=robustness,
                    run_descriptor_path=run,
                    output_directory=output,
                )
            self.assertFalse(output.exists())

    def test_rejects_run_descriptor_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results, robustness, run = self._reports(root)
            run.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(DataIntegrityError, "Run descriptor hash"):
                generate_gate_c_figures(
                    results_path=results,
                    robustness_path=robustness,
                    run_descriptor_path=run,
                    output_directory=root / "figures",
                )


if __name__ == "__main__":
    unittest.main()
