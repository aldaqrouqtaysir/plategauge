from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from plategauge.errors import DataIntegrityError
from plategauge.release_artifacts import FrozenFinalArtifact, read_json_object
from plategauge.release_robustness import (
    FROZEN_CONDITIONS,
    RobustnessCondition,
    _pair_for_condition,
    _predict_condition,
    _validate_quantiles,
    evaluate_frozen_robustness,
    torch_batch_predictor,
    unrelated_after_mapping,
    write_robustness_evidence,
)
from plategauge.robustness import Perturbation
from plategauge.schema import read_manifest

MANIFEST = Path("data/manifests/lefood_v1_manifest.csv")


def _artifact(root: Path) -> FrozenFinalArtifact:
    checkpoint = root / "checkpoint.pt"
    checkpoint.write_bytes(b"test")
    return FrozenFinalArtifact(
        experiment_directory=root,
        protocol_id="1" * 64,
        run_id="2" * 64,
        runner_fingerprint="3" * 64,
        configuration="M1",
        epoch=7,
        dropout=0.2,
        interval_correction=0.01,
        abstention_threshold=0.25,
        manifest_path=MANIFEST.resolve(),
        checkpoint_path=checkpoint,
        hashes={"checkpoint_sha256": "4" * 64},
        checkpoint_size_bytes=4,
    )


class ReleaseRobustnessTests(unittest.TestCase):
    def test_unrelated_mapping_is_full_cross_category_bijection(self) -> None:
        records = [record for record in read_manifest(MANIFEST) if record.is_valid]
        mapping = unrelated_after_mapping(records)
        self.assertEqual(len(mapping), 514)
        self.assertEqual(len({record.sample_id for record in mapping.values()}), 514)
        for record in records:
            self.assertNotEqual(mapping[record.sample_id].sample_id, record.sample_id)
            self.assertNotEqual(mapping[record.sample_id].category, record.category)

    def test_evidence_covers_every_condition_and_applies_only_routine_downgrade(self) -> None:
        def fake_prediction(*args: object, **kwargs: object) -> np.ndarray:
            records = args[0]
            condition = kwargs["condition"]
            targets = np.asarray([record.leftover_fraction for record in records], dtype=np.float32)
            if condition.group == "clean":
                median = targets
            elif condition.group == "routine_perturbation":
                median = np.clip(targets + 0.20, 0.0, 1.0)
            else:
                median = np.full_like(targets, 0.50)
            return np.stack(
                (np.clip(median - 0.05, 0.0, 1.0), median, np.clip(median + 0.05, 0.0, 1.0)),
                axis=1,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "plategauge.release_robustness._predict_condition",
                side_effect=fake_prediction,
            ):
                evidence = evaluate_frozen_robustness(
                    artifact=_artifact(root),
                    dataset_root=root,
                    predictor=lambda before, after: np.empty((len(before), 3)),
                    dataset_verification={"record_count": 524, "manifest_sha256": "5" * 64},
                    batch_size=16,
                )
            self.assertEqual(len(evidence["conditions"]), len(FROZEN_CONDITIONS))
            self.assertTrue(evidence["robustness_downgrade_required"])
            self.assertAlmostEqual(evidence["clean_macro_category_mae"], 0.0)
            for condition in evidence["conditions"]:
                self.assertEqual(condition["n"], 514)
                self.assertEqual(len(condition["predictions"]), 514)
                self.assertEqual(len(condition["predictions_sha256"]), 64)
                if condition["group"] == "misuse":
                    self.assertFalse(condition["exceeds_routine_downgrade_threshold"])
            output = root / "robustness.json"
            write_robustness_evidence(output, evidence)
            self.assertEqual(
                read_json_object(output)["evidence_sha256"], evidence["evidence_sha256"]
            )
            with self.assertRaisesRegex(DataIntegrityError, "already exists"):
                write_robustness_evidence(output, evidence)

    def test_rejects_invalid_quantiles_and_tampered_evidence(self) -> None:
        with self.assertRaisesRegex(DataIntegrityError, "ordered"):
            _validate_quantiles(np.asarray([[0.5, 0.4, 0.6]], dtype=np.float32), 1)
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(DataIntegrityError, "digest"),
        ):
            write_robustness_evidence(Path(directory) / "bad.json", {"evidence_sha256": "0" * 64})

    def test_condition_pairing_and_batched_preprocessing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (256, 256), (10, 20, 30)).save(root / "before.png")
            Image.new("RGB", (256, 256), (40, 50, 60)).save(root / "after.png")
            Image.new("RGB", (256, 256), (70, 80, 90)).save(root / "donor.png")
            record = type(
                "Record",
                (),
                {
                    "sample_id": "source",
                    "before_path": "before.png",
                    "after_path": "after.png",
                },
            )()
            donor = type("Donor", (), {"after_path": "donor.png"})()
            unrelated = {"source": donor}
            conditions = (
                RobustnessCondition("clean", "clean"),
                RobustnessCondition(
                    "brightness_plus_20pct",
                    "routine_perturbation",
                    perturbation=Perturbation("brightness_plus_20pct", "shared", 1.2),
                ),
                RobustnessCondition("same", "misuse", misuse="same_before_image"),
                RobustnessCondition("swapped", "misuse", misuse="swapped_order"),
                RobustnessCondition("unrelated", "misuse", misuse="unrelated_after"),
            )
            for condition in conditions:
                before, after = _pair_for_condition(
                    record,
                    dataset_root=root,
                    condition=condition,
                    unrelated=unrelated,
                )
                self.assertIsNotNone(before)
                self.assertIsNotNone(after)
            quantiles = _predict_condition(
                [record, record],
                dataset_root=root,
                condition=conditions[0],
                unrelated=unrelated,
                predictor=lambda before, after: np.tile(
                    np.asarray([[0.1, 0.2, 0.3]], dtype=np.float32), (len(before), 1)
                ),
                batch_size=1,
            )
            self.assertEqual(quantiles.shape, (2, 3))
            with self.assertRaises(ValueError):
                _predict_condition(
                    [record],
                    dataset_root=root,
                    condition=conditions[0],
                    unrelated=unrelated,
                    predictor=lambda before, after: np.zeros((1, 3), dtype=np.float32),
                    batch_size=0,
                )
            with self.assertRaisesRegex(DataIntegrityError, "Unsupported"):
                _pair_for_condition(
                    record,
                    dataset_root=root,
                    condition=RobustnessCondition("bad", "misuse"),
                    unrelated=unrelated,
                )

    def test_torch_predictor_adapter(self) -> None:
        import torch

        class TinyModel:
            def __call__(self, before: object, after: object) -> object:
                del after
                count = before.shape[0]  # type: ignore[union-attr]
                return torch.tensor([[0.1, 0.2, 0.3]]).repeat(count, 1)

        predictor = torch_batch_predictor(TinyModel(), device="cpu")
        values = predictor(
            np.zeros((2, 3, 2, 2), dtype=np.float32),
            np.zeros((2, 3, 2, 2), dtype=np.float32),
        )
        np.testing.assert_allclose(values, [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]])


if __name__ == "__main__":
    unittest.main()
