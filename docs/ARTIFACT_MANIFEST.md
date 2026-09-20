# Artifact manifest

This manifest summarizes the current evidence state. Machine-readable artifacts
and embedded hashes remain authoritative. Gate C approved the benchmark/failure
explorer form and memo claim boundaries on 20 September 2026; Gate D remains
pending, so none of these entries implies public-release approval.

A later pre-release audit found a mixed-line-ending clean-checkout defect in
the source-freeze tree. The release candidate adds only path-specific byte
contracts for the affected evidence classes. Frozen scientific values,
predictions, metrics, decisions, and model bytes are unchanged. See
`REPRODUCIBILITY_NOTE.md`.

## Frozen data and protocol

| Artifact | SHA-256 / identity | Status |
|---|---|---|
| `configs/frozen_folds.json` | `feb8143a9d8e238cefd0b60f629f7313a9962a53cca54b9c6783293ccaa4ecbe` | Active duplicate-safe outer folds |
| `configs/experiment.toml` | `58b9a9c1cdcfd4aa9dd6333f5bf29996e7123d01a7101c179b63af69166283a4` | Frozen confirmatory config |
| `data/manifests/lefood_v1_manifest.csv` | `0d8aae8e28b5aa8fcd5c35b89a40c7e90db55df893562043086485dde1f7ee16` | 514 valid pairs |
| `data/manifests/lefood_v1_audit.json` | `bd6322294895d474b1250b90e8f12c8a296ddf32156a8d5934a81367b1d63dd1` | Passed; zero leakage issues |
| Confirmatory run | `f1c7cfd1d13d16ecc9fc5f7d90ec9cb0394832741b3b786002c2b22be832eda4` | Complete and immutable |
| Protocol | `9450069d1260248bb5900c20c0b0784086513573735fb408c2bd2c85bb373e8f` | Active |
| Runner fingerprint | `89e6eaafe67abd780b399984bd3bf326696d4a8dda8b6cbaffd0ba95f242a5ca` | Bound to run |

The historical data-gate and fold-amendment files are preserved as issued and
remain the decision history for D011/D012.

## Gate C evidence

| Artifact | File SHA-256 | Status / role |
|---|---|---|
| `reports/results.json` | `75d653292e34f1ad31118c5cf6249027ba3395f449bdcdeba717a94bc9444c12` | Canonical metrics, slices, gates, recommendation |
| `reports/bootstrap_comparisons.json` | `07a4a5aa76da3d63147e1cd8aa0084ab8324106a8f5932f374d561f839bac3f1` | Bootstrap/sign-flip comparisons |
| `reports/robustness.json` | `ba9e75328a5066681770d952293e7828d0de4b4de1a413505bab359494314fe6` | Final-model sensitivity; embedded evidence `f62a467…fe0c2` |
| `reports/error_analysis.json` | `16d4cf8099e307692b102aedb1e17fda55145ec77ebf1f54426ed8028cf93df9` | Immutable top/bottom rankings; embedded evidence `534b181…f23b5` |
| `reports/error_review_annotations.csv` | `17818944cfbc60662e10f7dcb3a8f5df3f7f9451971bba5d99792804339f8f6c` | Separate AI-assisted post hoc visual review |
| `reports/label_sensitivity.json` | `ea747a3886bcfd169584405ed576970c9843331e188e8e681848235fd39400f1` | Post hoc four-row sensitivity; no frozen-result change |
| `configs/same_category_folds_v1.json` | `961fc17d826bf16637d31208c0743139a5ef47548e7bc6e9a56641a4f2ae387d` | Frozen duplicate-safe diagnostic folds |
| Gate C as-issued `reports/experiments/same_category_v1/summary.json` | `f6d04d6fe585314b51af5d30e1d442695a52db6b91d037e1d0dd1fea47977dd0` | Preserved inside `outputs/PlateGauge_Gate_C_Source_and_Evidence_2026-09-20.zip`; original run ID `d4819024…2169` |
| Release-sanitized `reports/experiments/same_category_v1/summary.json` | `5d989d9d6ff0f2912b33137013b0ce37a3c9db7d65f976c68356f66d2df7dd08` | Same predictions and metrics; build-host path removed; sanitized run ID `5a6f6c49…7e5c`; bridge: `reports/release/same-category-provenance-sanitization.json` |

## Model export

| Artifact | Size | SHA-256 / status |
|---|---:|---|
| Final PyTorch checkpoint | 10,439,997 bytes | `cc93461273626415af12eaa5217f4bfb76668a3fcb27f6338c4bda3a6035fef4` |
| `artifacts/plategauge.onnx` | 10,355,122 bytes | `9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675` |
| `artifacts/plategauge.onnx.evidence.json` | 3,591 bytes | File `cea7f533fa53388345c5ea45828bc9d3dd20cc79a013c3c843b6f2d5f9268c54`; embedded `210cca0…e89c6` |
| Parity | 8 samples | Maximum drift `5.185604095458984e-06`; pass |
| `web/public/models/plategauge.onnx` | 10,355,122 bytes | Staged byte-identical copy; SHA-256 `9c830e80…675` |
| `web/public/models/release.json` | 438 bytes | Candidate metadata `v1.0.0`; SHA-256 `76be7ee370b709235675c97119a4194d9b2e8220ad42734ada98f9b99c4cd599`; release authorization remains separate |
| `reports/browser_benchmark.json` | 2,256 bytes | File SHA-256 `73a2ad2a4c945964b608edb4520adb9dcc97d53368e6fe9756b71691a94a3a2f`; evidence `77dc5e9…7be9`; source measurement `3c194e8…a71f1`; all gates pass |
| `web/src/generated/benchmarkEvidence.json` and staged public copy | 10 displayed examples / 18 canonical sources | Byte-identical copies; SHA-256 `c6f7d435d077bc67649d192efb169e247a1a208e5e9bdc0b6feabd772887c412`; fail-closed verifier passes |

## Deterministic figures

| Figure | SHA-256 |
|---|---|
| `reports/figures/gate_c_workload_macro_mae.svg` | `c22912f2c1196f67b8bc2da114c049d2898988be41a88e2de5fe82255024c1f6` |
| `reports/figures/gate_c_paired_vs_after_only_by_category.svg` | `11629a8bfb532eb04dc014a8e4a29d2cff823e4fb9c91eaedfc0b5aa83a2595e` |
| `reports/figures/gate_c_target_slice_micro_mae.svg` | `1bf6c636b9c081e4cd526b245f58ff7406835a433f2f6daec8a78f2523ee4239` |
| `reports/figures/gate_c_routine_robustness_delta.svg` | `27879700e1f529003384ec7a84beebe613ebf79e29cb39fbe7bfd175f83cdcae` |

## Documentation and governance

`README.md`, `docs/RESULTS.md`, `ERROR_ANALYSIS.md`, `ROBUSTNESS.md`,
`MODEL_CARD.md`, `SYSTEM_CARD.md`, `CLAIM_EVIDENCE_MAP.csv`, and
`RESEARCH_DECISIONS.md`, plus `REPRODUCIBILITY_NOTE.md`, reflect the frozen evidence and the Gate C product
boundary. Detailed internal decision, AI-assistance, contribution, and
continuity records remain outside the prospective public source tree.

## Local release-candidate evidence

| Artifact | Status / role |
|---|---|
| `reports/release/static-bundle-audit.json` | Exact 36-file production inventory; digest `19bddecb…4485`; no unexpected resource |
| `reports/release/production-smoke-observation.json` | 2/2 local production-path Chromium checks passed, including real fixed-pair ONNX inference |
| Pre-remediation private Gate D draft under workspace `outputs/` | The 591-file source/evidence archive is superseded by the public-boundary remediation and must not be distributed; rebuild and re-audit the package from the current prospective tree before Gate D |
| Private review backup under workspace `outputs/` | Exact external hashes are recorded in its private manifest; it is not part of the prospective public source tree or a release |

Internal planning, detailed contribution/AI, continuity, and review records are
deliberately absent from the prospective public source archive. Public
transparency is provided by `docs/AUTHORSHIP.md`,
`docs/AI_ASSISTANCE_PUBLIC.md`, and `docs/RESEARCH_DECISIONS.md`.

## Still unavailable

- Applicant-performed independent reproduction and final
  contribution/authorship sign-off. Cross-platform corrective verification is
  system-executed evidence and does not establish applicant mastery.
- Immutable source commit and history scan, Gate D approval record,
  `v1.0.0` tag, remote repository, protected Pages environment, deployed URL,
  build ID, live public smoke, and rollback evidence.
