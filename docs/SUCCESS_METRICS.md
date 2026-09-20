# Success metrics and gates

These thresholds were chosen before confirmatory results. “Pass” means the
project may make a narrowly worded benchmark claim; it does not establish field
utility.

## Data integrity

- At least 500 valid paired observations.
- Dataset and checkpoint licenses recorded.
- Filename-to-row pairing, source version, hashes, dimensions, target, category,
  exclusions, duplicate group, and split recorded.
- No exact or confirmed near-duplicate component crosses an outer fold.

## Model value

- Primary: macro-category MAE across all 34 held-out categories.
- Paired-value pass: MobileNet macro-category MAE at least 5% below after-only
  MobileNet and 10% below the best non-neural baseline.
- Superiority wording additionally requires the paired category-bootstrap 95%
  interval for improvement to exclude no improvement.

## Public numeric demo

- Macro-category MAE ≤0.10.
- 90th-percentile absolute error ≤0.25.
- No broad target-slice MAE >0.15.
- If MAE is greater than 0.10 and at most 0.15, or the improvement interval
  includes zero, publish an evaluation/failure explorer rather than an
  unrestricted estimator.
- If MAE is greater than 0.15 and at most 0.20, publish only a negative research
  record and failure analysis, with no upload-based estimator.
- If MAE >0.20 or the model fails both median and handcrafted baselines, stop.

## Uncertainty and abstention

- Display an “empirical 90% interval” only if aggregate outer coverage is
  85–95%, mean width ≤0.30, and coverage ≥80% in every broad target slice.
- Claim useful abstention only if roughly 80% retention lowers macro-category
  MAE by at least 20% and retains ≥50% of every broad target slice.

## Efficiency and product behavior

- Exported MobileNet ≤15 MB FP32.
- Maximum absolute PyTorch–ONNX prediction drift ≤`1e-4` on the parity set.
- MobileNet macro-MAE no more than 0.02 worse than DINOv2 for the efficiency
  framing.
- UINT8 ships only if relative MAE worsens ≤2% and measured latency improves
  ≥10%; otherwise FP32 ships.
- On the documented reference laptop, warm browser p95 paired inference ≤1.5 s
  and peak application memory ≤512 MB.
- All required CI checks pass, no selected image content is uploaded, and no
  critical accessibility or security issue remains.

## Release-readiness evidence

- Every public claim is supported in `CLAIM_EVIDENCE_MAP.csv`.
- Frozen success and failure examples are reviewed against their source rows.
- Any independent-reproduction or contribution claim has separate, dated
  evidence; it is not inferred from repository completeness.
- Demo, repository, cards, public disclosures, and result wording agree.
