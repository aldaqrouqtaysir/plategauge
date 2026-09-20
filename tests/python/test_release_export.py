from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from plategauge.data import sha256_file
from plategauge.errors import DataIntegrityError
from plategauge.release_artifacts import FrozenFinalArtifact, read_json_object
from plategauge.release_export import (
    MAXIMUM_FP32_MODEL_BYTES,
    compose_export_evidence,
    export_frozen_onnx_with_evidence,
)


def _artifact(root: Path) -> FrozenFinalArtifact:
    checkpoint = root / "checkpoint.pt"
    checkpoint.write_bytes(b"checkpoint")
    return FrozenFinalArtifact(
        experiment_directory=root,
        protocol_id="1" * 64,
        run_id="2" * 64,
        runner_fingerprint="3" * 64,
        configuration="M1",
        epoch=5,
        dropout=0.2,
        interval_correction=0.01,
        abstention_threshold=0.25,
        manifest_path=root / "manifest.csv",
        checkpoint_path=checkpoint,
        hashes={"checkpoint_sha256": "4" * 64},
        checkpoint_size_bytes=checkpoint.stat().st_size,
    )


class ReleaseExportTests(unittest.TestCase):
    def test_composes_hash_bound_gate_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = compose_export_evidence(
                artifact=_artifact(Path(directory)),
                dataset_verification={"manifest_sha256": "5" * 64},
                model_filename="plategauge.onnx",
                model_sha256="6" * 64,
                model_bytes=1024,
                export_metadata={"onnx_sha256": "6" * 64},
                parity_sample_ids=[f"sample-{index}" for index in range(8)],
                parity_input_sha256="7" * 64,
                maximum_parity_drift=1e-6,
            )
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["onnx"]["model_bytes"], 1024)
        self.assertTrue(evidence["parity"]["passed"])
        self.assertFalse(evidence["implicit_downloads_allowed"])
        self.assertEqual(len(evidence["evidence_sha256"]), 64)

    def test_rejects_size_drift_and_nonunique_parity_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = _artifact(Path(directory))
            common = {
                "artifact": artifact,
                "dataset_verification": {},
                "model_filename": "model.onnx",
                "model_sha256": "6" * 64,
                "export_metadata": {},
                "parity_input_sha256": "7" * 64,
            }
            with self.assertRaisesRegex(DataIntegrityError, "maximum"):
                compose_export_evidence(
                    **common,
                    model_bytes=MAXIMUM_FP32_MODEL_BYTES + 1,
                    parity_sample_ids=[str(index) for index in range(8)],
                    maximum_parity_drift=0.0,
                )
            with self.assertRaisesRegex(DataIntegrityError, "drift"):
                compose_export_evidence(
                    **common,
                    model_bytes=10,
                    parity_sample_ids=[str(index) for index in range(8)],
                    maximum_parity_drift=0.001,
                )
            with self.assertRaisesRegex(DataIntegrityError, "unique"):
                compose_export_evidence(
                    **common,
                    model_bytes=10,
                    parity_sample_ids=["same"] * 8,
                    maximum_parity_drift=0.0,
                )

    def test_exports_to_temporary_path_then_publishes_model_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = _artifact(root)
            before = np.zeros((8, 3, 224, 224), dtype=np.float32)
            after = np.ones((8, 3, 224, 224), dtype=np.float32)

            def exporter(model: object, path: Path, **kwargs: object) -> dict[str, object]:
                del model, kwargs
                path.write_bytes(b"valid-onnx-test-bytes")
                return {"onnx_sha256": sha256_file(path), "opset_version": 18}

            output = root / "release" / "plategauge.onnx"
            evidence_path = root / "release" / "plategauge.onnx.evidence.json"
            with patch(
                "plategauge.release_export._parity_inputs",
                return_value=([f"sample-{index}" for index in range(8)], before, after),
            ):
                evidence = export_frozen_onnx_with_evidence(
                    artifact=artifact,
                    model=object(),
                    dataset_root=root,
                    dataset_verification={"record_count": 524},
                    output_path=output,
                    evidence_path=evidence_path,
                    exporter=exporter,
                    parity_checker=lambda model, path, left, right: 1e-7,
                )
            self.assertEqual(sha256_file(output), evidence["onnx"]["sha256"])
            self.assertEqual(read_json_object(evidence_path), evidence)
            with (
                patch(
                    "plategauge.release_export._parity_inputs",
                    return_value=([f"sample-{index}" for index in range(8)], before, after),
                ),
                self.assertRaisesRegex(DataIntegrityError, "already exists"),
            ):
                export_frozen_onnx_with_evidence(
                    artifact=artifact,
                    model=object(),
                    dataset_root=root,
                    dataset_verification={},
                    output_path=output,
                    evidence_path=evidence_path,
                    exporter=exporter,
                    parity_checker=lambda model, path, left, right: 0.0,
                )


if __name__ == "__main__":
    unittest.main()
