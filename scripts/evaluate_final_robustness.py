"""Evaluate the frozen final model under preregistered robustness conditions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from plategauge.data import DEFAULT_AUDIT_REPORT, DEFAULT_DATASET_ROOT, DEFAULT_MANIFEST
from plategauge.orchestration import verify_dataset_root
from plategauge.release_artifacts import load_frozen_paired_model, validate_frozen_final_artifact
from plategauge.release_robustness import (
    evaluate_frozen_robustness,
    torch_batch_predictor,
    write_robustness_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the immutable 514-pair clean/perturbation/misuse evaluation."
    )
    parser.add_argument("--experiment-directory", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.toml"))
    parser.add_argument("--folds", type=Path, default=Path("configs/frozen_folds.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/robustness.json"))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--batch-size", type=int, default=32)
    arguments = parser.parse_args()

    artifact = validate_frozen_final_artifact(
        experiment_directory=arguments.experiment_directory,
        audit_report_path=arguments.audit_report,
        manifest_path=arguments.manifest,
        config_path=arguments.config,
        folds_path=arguments.folds,
    )
    dataset_verification = verify_dataset_root(arguments.manifest, arguments.dataset_root)
    model = load_frozen_paired_model(artifact, device=arguments.device)
    evidence = evaluate_frozen_robustness(
        artifact=artifact,
        dataset_root=arguments.dataset_root,
        predictor=torch_batch_predictor(model, device=arguments.device),
        dataset_verification=dataset_verification,
        batch_size=arguments.batch_size,
    )
    write_robustness_evidence(arguments.output, evidence)
    print(
        json.dumps(
            {
                "output": str(arguments.output),
                "evidence_sha256": evidence["evidence_sha256"],
                "condition_count": len(evidence["conditions"]),
                "robustness_downgrade_required": evidence["robustness_downgrade_required"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
