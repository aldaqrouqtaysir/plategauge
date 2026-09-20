# PlateGauge model card

> **Frozen research model; benchmark artifact only.** The model and evaluation
> artifacts are complete. Gate C approved a benchmark/failure explorer and the
> review memo's claim boundaries on 20 September 2026. The failed numeric-demo
> and uncertainty gates prohibit presenting this model as a reliable
> user-facing estimator, whether or not an authorized release later ships the
> exact bytes as a reproducibility artifact.

## Model details

- Name/version: `plategauge/9450069d1260/cc9346127362`.
- Task: predict recorded leftover fraction from a standardized before/after
  single-item image pair.
- Architecture: shared MobileNetV3-Small encoder; fusion of before, after,
  absolute difference, and elementwise product; 256-unit head; ordered 0.05,
  0.50, and 0.95 outputs.
- Selected configuration: M2, dropout `0.4`, final epoch `6`.
- Base checkpoint: `timm/mobilenetv3_small_100.lamb_in1k`, revision
  `1824797e7887cbec1990e4adbd6675960a36c589`, weight SHA-256
  `46d2c063b18125884c48937afa4c49e18128869e52e8db96df48bf0a4d7ff697`.
- Confirmatory seed: `20260919`.
- Training data: all 514 valid LeFood-Set v1 pairs for the final artifact;
  category-disjoint outer predictions are the performance evidence.
- License: project/base checkpoint Apache-2.0; source data CC BY 4.0. The trained
  artifact is dataset-derived and requires attribution/change notices.

## Inputs and outputs

Inputs are two 224×224 normalized RGB tensors named `before` and `after`.
Food label, category, weights, observer score, filename, and EXIF are not model
inputs. Outputs are ordered `[q05, q50, q95]` values bounded to `[0,1]`.

Those names describe the raw ONNX outputs. In the primary outer prediction CSVs,
the legacy `q05` and `q95` fields were overwritten with each fold's corrected
and clipped empirical interval endpoints; raw outer endpoints were not retained
as separate columns. `q50` remains the model point prediction.

The frozen inner-derived policy has interval correction
`0.03567694687261813` and width threshold `0.3`. These values are retained for
analysis, but the public interval and useful-abstention gates failed. They must
not be exposed as a guaranteed or operational confidence system.

## Evaluation

Primary category-disjoint metrics over 514 outer predictions and 34 categories:

| Metric | Value |
|---|---:|
| Macro-category MAE | `0.12275587386595668` |
| Micro MAE | `0.13392757808175082` |
| RMSE | `0.21968641494432023` |
| Signed bias | `-0.060243876984511696` |
| P90 absolute error | `0.38161105546813745` |
| Spearman | `0.8548378735024158` |

The paired model is worse than after-only MobileNet by
`+0.024898287038787673` macro-category MAE, with bootstrap 95% interval
`[0.007664708956515841, 0.043684385882585365]`. It is better than handcrafted
Ridge by `0.12874773491229044`; the paired-minus-Ridge interval is entirely
below zero. The public numeric-demo gate fails.

The category bootstrap is conditional on the 34 observed category errors and
the fixed folds, seed, recipe, and predictions. It does not include retraining,
alternative-split, site, cuisine, or deployment-population uncertainty.

The empirical interval has aggregate coverage `0.9319066147859922`, mean width
`0.6672064520552123`, and minimum broad-slice coverage
`0.8297872340425532`; it fails the width gate. The width rule retains only
`0.2529182879377432` overall and `0.02127659574468085` in its least-retained
broad slice, so no useful-abstention claim is allowed.

## Export

- Checkpoint SHA-256:
  `cc93461273626415af12eaa5217f4bfb76668a3fcb27f6338c4bda3a6035fef4`;
  10,439,997 bytes.
- FP32 ONNX SHA-256:
  `9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675`;
  10,355,122 bytes; opset 18.
- Maximum PyTorch/ONNX drift: `5.185604095458984e-06` on eight frozen samples;
  threshold `1e-4`; pass.
- Export sidecar file SHA-256:
  `cea7f533fa53388345c5ea45828bc9d3dd20cc79a013c3c843b6f2d5f9268c54`.
- Local browser staging: byte-identical ONNX with candidate metadata version
  `v1.0.0`; this version consistency does not imply deployment or release approval.
- Physical browser: headed Chrome `152.0.7977.83` on HP Laptop 15-fd0xxx,
  i7-1355U, 15.652 GiB RAM, Windows `10.0.22631`; 3 warm-ups and 20
  measurements; nearest-rank p50 `18.78000009059906` ms and p95
  `22.119999885559082` ms; peak application memory
  `45.64192485809326` MiB via
  `performance.measureUserAgentSpecificMemory`; first-load body bytes
  `25,128,921`; both frozen browser gates passed.
- Browser evidence digest:
  `77dc5e9ee873fc453f6a081926dc2259f675c6fbf39a5e1e3e73f5053bf77be9`;
  source measurement SHA-256
  `3c194e85724fda14550253a7994c34bd0c46026722cc80d1733767cb042a71f1`.

Browser performance is supported only for this measured reference environment.
No phone, unmeasured-browser, or universal-speed claim is allowed.

## Gate C-approved intended use

Research reproduction, benchmark comparison, and an interactive failure
explorer for a controlled single-item dataset. The model may support examples
that explain error modes, but it should not be offered as an unrestricted
numeric estimator under the failed gates.

## Out-of-scope use

Mixed meals, arbitrary photographs, live video, calories/nutrition, clinical
intake, diagnosis, procurement, billing, monitoring people, consequential
automation, scale replacement, food-waste reduction claims, or geographic and
cuisine generalization.

## Limitations and risks

- One controlled Indonesian hospital acquisition context; unknown external
  validity.
- The 154 workbook rows without archived images are the complete block of source
  categories `034`–`049`; results cover only image categories `000`–`033`.
- Small and unequal category supports, including singleton categories.
- Endpoint-heavy targets: 207 exact zeros and 47 exact ones, or 254/514
  (`49.4%`) at a boundary.
- Material underestimation in nonzero and high-leftover slices.
- Possible image-to-mass tensions that cannot be adjudicated from the public
  source alone.
- Paired input did not add value over after-only inference in the primary
  evaluation.
- After-image blur breached the frozen perturbation-downgrade threshold.
- The model can be confidently wrong; narrow intervals occurred on some of the
  largest errors.
- No formal conformal guarantee, field validation, user study, or impact study.

## Reproducibility identity

- Run ID:
  `f1c7cfd1d13d16ecc9fc5f7d90ec9cb0394832741b3b786002c2b22be832eda4`.
- Protocol ID:
  `9450069d1260248bb5900c20c0b0784086513573735fb408c2bd2c85bb373e8f`.
- Runner fingerprint:
  `89e6eaafe67abd780b399984bd3bf326696d4a8dda8b6cbaffd0ba95f242a5ca`.
- Manifest SHA-256:
  `0d8aae8e28b5aa8fcd5c35b89a40c7e90db55df893562043086485dde1f7ee16`.

At the 20 September 2026 source-freeze review, no release tag, public URL,
release commit, maintainer sign-off, or Gate D approval existed. Any later
release status must be verified from the checked-out tag's approval record and
release evidence; it does not broaden this model card's scientific claims.
