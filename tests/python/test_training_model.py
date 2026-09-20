from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from plategauge.errors import OptionalDependencyError
from plategauge.model import (
    MOBILENET_CHECKPOINT,
    PairedQuantileRegressor,
    build_timm_encoder,
    torch_available,
)
from plategauge.training import (
    InnerRun,
    SelectedConfiguration,
    select_final_training_choice,
    select_inner_configuration,
)
from plategauge.uncertainty import ordered_quantiles_numpy


class SelectionTests(unittest.TestCase):
    def test_exact_configuration_tie_prefers_m1(self) -> None:
        runs = [
            InnerRun(configuration, fold, 10 + fold, 0.1)
            for configuration in ("M1", "M2")
            for fold in range(4)
        ]
        selected = select_inner_configuration(runs)
        self.assertEqual(selected.configuration, "M1")
        self.assertEqual(selected.epoch, 11)  # int(median(10, 11, 12, 13))

    def test_final_modal_configuration_and_median_epoch(self) -> None:
        selections = [
            SelectedConfiguration("M2", 10, 0.10),
            SelectedConfiguration("M1", 12, 0.11),
            SelectedConfiguration("M2", 14, 0.09),
            SelectedConfiguration("M1", 16, 0.12),
            SelectedConfiguration("M2", 18, 0.08),
        ]
        selected = select_final_training_choice(selections)
        self.assertEqual(selected.configuration, "M2")
        self.assertEqual(selected.epoch, 14)

    def test_final_epoch_uses_all_five_outer_selections(self) -> None:
        selections = [
            SelectedConfiguration("M2", 1, 0.10),
            SelectedConfiguration("M2", 2, 0.10),
            SelectedConfiguration("M2", 3, 0.10),
            SelectedConfiguration("M1", 70, 0.10),
            SelectedConfiguration("M1", 80, 0.10),
        ]
        selected = select_final_training_choice(selections)
        self.assertEqual(selected.configuration, "M2")
        self.assertEqual(selected.epoch, 3)


class OptionalModelTests(unittest.TestCase):
    def test_numpy_contract_matches_ordering_invariants(self) -> None:
        result = ordered_quantiles_numpy(np.zeros((2, 3)))
        self.assertTrue(np.allclose(result[0], [0.25, 0.5, 0.75]))

    @unittest.skipIf(torch_available(), "minimal-dependency behavior only")
    def test_missing_torch_has_actionable_error(self) -> None:
        with self.assertRaisesRegex(OptionalDependencyError, "torch.*train"):
            PairedQuantileRegressor(None, 1024, dropout=0.2)

    @unittest.skipUnless(torch_available(), "Torch is required to enter the timm construction path")
    def test_pinned_checkpoint_loads_before_classifier_is_removed(self) -> None:
        class FakeEncoder:
            head_hidden_size = 1024
            num_features = 576

            def __init__(self) -> None:
                self.reset_calls: list[tuple[int, str]] = []

            def reset_classifier(self, classes: int, *, global_pool: str) -> None:
                self.reset_calls.append((classes, global_pool))

        encoder = FakeEncoder()
        fake_timm = mock.Mock()
        fake_timm.create_model.return_value = encoder
        weights = Path("pinned-model.safetensors")

        with (
            mock.patch("plategauge.model._require_timm", return_value=fake_timm),
            mock.patch("plategauge.model.verify_mobilenet_weights", return_value=weights),
        ):
            built, feature_dimension = build_timm_encoder(
                MOBILENET_CHECKPOINT,
                pretrained=True,
                weights_path=weights,
            )

        self.assertIs(built, encoder)
        self.assertEqual(feature_dimension, 1024)
        fake_timm.create_model.assert_called_once_with(
            MOBILENET_CHECKPOINT,
            pretrained=False,
            checkpoint_path=str(weights),
        )
        self.assertEqual(encoder.reset_calls, [(0, "avg")])


if __name__ == "__main__":
    unittest.main()
