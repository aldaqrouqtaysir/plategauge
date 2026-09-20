"""Export the validated final checkpoint and immutable ONNX evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from plategauge.data import DEFAULT_AUDIT_REPORT, DEFAULT_DATASET_ROOT, DEFAULT_MANIFEST
from plategauge.orchestration import verify_dataset_root
from plategauge.release_artifacts import load_frozen_paired_model, validate_frozen_final_artifact
from plategauge.release_export import export_frozen_onnx_with_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export only a hash-validated final PlateGauge checkpoint; never download weights."
    )
    parser.add_argument("--experiment-directory", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.toml"))
    parser.add_argument("--folds", type=Path, default=Path("configs/frozen_folds.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/plategauge.onnx"))
    parser.add_argument(
        "--evidence", type=Path, default=Path("artifacts/plategauge.onnx.evidence.json")
    )
    arguments = parser.parse_args()

    artifact = validate_frozen_final_artifact(
        experiment_directory=arguments.experiment_directory,
        audit_report_path=arguments.audit_report,
        manifest_path=arguments.manifest,
        config_path=arguments.config,
        folds_path=arguments.folds,
    )
    dataset_verification = verify_dataset_root(arguments.manifest, arguments.dataset_root)
    # CPU loading makes the PyTorch side of the parity check explicit and
    # portable. build_paired_model(pretrained=False) cannot contact a registry.
    model = load_frozen_paired_model(artifact, device="cpu")
    evidence = export_frozen_onnx_with_evidence(
        artifact=artifact,
        model=model,
        dataset_root=arguments.dataset_root,
        dataset_verification=dataset_verification,
        output_path=arguments.output,
        evidence_path=arguments.evidence,
    )
    print(
        json.dumps(
            {
                "model": str(arguments.output),
                "evidence": str(arguments.evidence),
                "model_sha256": evidence["onnx"]["sha256"],
                "model_bytes": evidence["onnx"]["model_bytes"],
                "maximum_absolute_drift": evidence["parity"]["maximum_absolute_drift"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
