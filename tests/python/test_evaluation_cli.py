from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from plategauge.cli import main
from plategauge.evaluation import (
    PredictionRecord,
    evaluate_predictions,
    read_predictions,
    write_predictions,
)
from plategauge.schema import ManifestRecord


class PredictionTests(unittest.TestCase):
    def records(self) -> list[PredictionRecord]:
        categories = ("001", "001", "002", "002", "029", "029")
        folds = (0, 0, 1, 1, 2, 2)
        return [
            PredictionRecord(
                sample_id=f"sample-{index}",
                category=categories[index],
                outer_fold=folds[index],
                target=target,
                q05=max(0.0, target - 0.1),
                q50=target,
                q95=min(1.0, target + 0.1),
                configuration="M1",
                epoch=10,
            )
            for index, target in enumerate((0.0, 0.2, 0.4, 0.6, 0.8, 1.0))
        ]

    def manifest(self) -> list[ManifestRecord]:
        return [
            ManifestRecord(
                sample_id=record.sample_id,
                source_row=index + 2,
                food_name="test",
                category=record.category,
                before_path=f"before/{index}.jpg",
                after_path=f"after/{index}.jpg",
                before_mass_g=100.0,
                after_mass_g=record.target * 100.0,
                leftover_fraction=record.target,
                observer_score=4,
                before_width=224,
                before_height=224,
                after_width=224,
                after_height=224,
                before_sha256=f"{index + 1:064x}",
                after_sha256=f"{index + 101:064x}",
                outer_fold=record.outer_fold,
            )
            for index, record in enumerate(self.records())
        ]

    def test_prediction_round_trip_and_evaluation(self) -> None:
        records = self.records()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            write_predictions(records, path)
            loaded = read_predictions(path)
        self.assertEqual(loaded, records)
        result = evaluate_predictions(loaded, self.manifest())
        self.assertEqual(result["overall"]["micro_mae"], 0.0)
        self.assertEqual(len(result["twenty_largest_errors"]), 6)

    def test_manifest_binding_rejects_missing_or_changed_rows(self) -> None:
        records = self.records()
        with self.assertRaisesRegex(ValueError, "do not match"):
            evaluate_predictions(records[:-1], self.manifest())
        changed = list(records)
        source = changed[0]
        changed[0] = PredictionRecord(
            source.sample_id,
            source.category,
            source.outer_fold,
            0.123,
            source.q05,
            source.q50,
            source.q95,
            source.configuration,
            source.epoch,
        )
        with self.assertRaisesRegex(ValueError, "Target mismatch"):
            evaluate_predictions(changed, self.manifest())

    def test_unordered_quantiles_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ordered"):
            PredictionRecord("x", "000", 0, 0.5, 0.7, 0.5, 0.8, "M1", 1)

    def test_canonical_schema_round_trips_non_neural_workload(self) -> None:
        record = PredictionRecord(
            sample_id="baseline",
            category="001",
            outer_fold=0,
            target=0.4,
            q05=0.5,
            q50=0.5,
            q95=0.5,
            configuration="",
            epoch=0,
            workload="training_median",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.csv"
            write_predictions([record], path)
            self.assertEqual(read_predictions(path), [record])
        with self.assertRaisesRegex(ValueError, "must not claim"):
            PredictionRecord(
                "bad", "001", 0, 0.4, 0.5, 0.5, 0.5, "M1", 0, "training_median"
            )


class CliTests(unittest.TestCase):
    def test_doctor_is_json_and_succeeds(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["doctor"])
        payload = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertIn("numpy", payload["dependencies"])


if __name__ == "__main__":
    unittest.main()
