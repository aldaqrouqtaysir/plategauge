# Results

> **Frozen evidence; Gate C approved 20 September 2026.** The confirmatory run
> is complete and immutable. Gate C approved the
> `benchmark_failure_explorer` form and the Gate C review memo's claim
> boundaries. This report does not itself grant release authority or authorize
> replacing the paired model with an after-only product; any release authority
> must be verified from the tagged Gate D approval record.

## Dataset and protocol identity

- 514 valid pairs across 34 categories; fold sizes 103/103/103/103/102.
- The 154 workbook rows without archived image pairs are all in the 16 source
  categories `034`–`049`; the evaluated image benchmark covers categories
  `000`–`033` and is not a random sample of the 50-category workbook.
- Run ID:
  `f1c7cfd1d13d16ecc9fc5f7d90ec9cb0394832741b3b786002c2b22be832eda4`.
- Protocol ID:
  `9450069d1260248bb5900c20c0b0784086513573735fb408c2bd2c85bb373e8f`.
- Manifest SHA-256:
  `0d8aae8e28b5aa8fcd5c35b89a40c7e90db55df893562043086485dde1f7ee16`.
- Canonical evidence: `reports/results.json` and
  `reports/bootstrap_comparisons.json`.

## Confirmatory performance

| Workload | Macro-category MAE | Role |
|---|---:|---|
| Observer score | 0.092468 | Contextual reference only; not a deployable model |
| After-only MobileNet | 0.097858 | Required ablation |
| Frozen paired DINOv2 | 0.103261 | Heavy representation reference |
| **Paired MobileNet** | **0.122756** | Primary confirmatory model |
| Paired ResNet-50 | 0.159984 | Architecture-family control |
| Handcrafted paired Ridge | 0.251504 | Best non-neural baseline |
| Training-fold median | 0.374378 | Constant baseline |
| Wrong-pair control | 0.389359 | Destructive mismatch control; not a before-image contribution test |

Exact paired-MobileNet metrics:

| Metric | Value |
|---|---:|
| Macro-category MAE | `0.12275587386595668` |
| Micro MAE | `0.13392757808175082` |
| RMSE | `0.21968641494432023` |
| Signed bias | `-0.060243876984511696` |
| Median absolute error | `0.055020540207624424` |
| 90th-percentile absolute error | `0.38161105546813745` |
| Spearman correlation | `0.8548378735024158` |
| Within ±0.10 | `0.6167315175097277` |
| Within ±0.20 | `0.72568093385214` |

## Predefined comparisons

The paired model was worse than after-only MobileNet by
`0.024898287038787673` macro-category MAE. The paired category-bootstrap 95%
interval was `[0.007664708956515841, 0.043684385882585365]`; the Holm-adjusted
sign-flip p-value was `0.00993990060099399`. The preregistered paired-value gate
therefore failed.

The bootstrap resamples the 34 observed category-level error differences while
holding the frozen folds, seed, model recipe, and predictions fixed. Its interval
does not incorporate retraining variability, alternative category assignments,
acquisition sites, cuisines, or a defined deployment population. The inference
is therefore conditional on this exact run and benchmark.

The paired model was better than handcrafted Ridge by
`0.12874773491229044` macro-category MAE. For the signed paired-minus-Ridge
difference, the estimate was `-0.12874773491229044` with 95% interval
`[-0.16929860291150312, -0.08777214659223792]`. This supports a narrow
dataset/protocol-specific representation-learning claim, not general
superiority.

## Target-range errors

| Target range | n | Micro MAE |
|---|---:|---:|
| Exact zero | 207 | 0.023365 |
| (0, 0.25] | 59 | 0.102301 |
| (0.25, 0.50] | 60 | 0.199491 |
| (0.50, 0.75] | 57 | **0.274511** |
| (0.75, 1) | 84 | 0.226371 |
| Exact one | 47 | 0.241165 |

Exact zero and exact one together account for 254/514 targets (`49.4%`). The
low exact-zero error therefore must not be used to obscure the much larger
interior and exact-one errors.

The negative signed bias and high errors in nonzero, high-leftover slices show a
material underestimation pattern. No broad-slice validity claim is supported.

## Empirical-interval artifact semantics

In the primary outer paired-MobileNet prediction CSVs, the legacy fields named
`q05` and `q95` contain the fold-specific empirically corrected and `[0,1]`-
clipped interval endpoints. They overwrite rather than separately preserve the
raw model quantiles; `q50` remains the point prediction. The exported ONNX model
emits the raw ordered three-value output. Because the interval gate failed, no
corrected or raw interval is presented as useful, guaranteed, or conformal.

## Frozen gate outcomes

| Gate | Frozen rule | Outcome |
|---|---|---|
| Paired value | ≥5% improvement over after-only and ≥10% over best non-neural | **Fail**: `-25.443%` versus after-only; `+51.191%` versus Ridge |
| Superiority wording | both paired bootstrap upper bounds below zero | **Fail** |
| Public numeric demo | macro MAE ≤0.10; P90 ≤0.25; every broad slice ≤0.15 | **Fail**: `0.122756`, `0.381611`, `0.274511` |
| Interval display | coverage 85–95%; mean width ≤0.30; slice coverage ≥80% | **Fail**: coverage `0.931907`, width `0.667206`, minimum slice coverage `0.829787` |
| Useful abstention | ≥20% error reduction and ≥50% retention in every broad slice | **Fail**: `78.574%` reduction, but `25.292%` overall and `2.128%` minimum-slice retention |
| Efficiency | DINO gap ≤0.02; FP32 ≤15,000,000 bytes; drift ≤1e-4 | **Pass** |
| Stop | macro MAE >0.20 or fails both median and handcrafted baselines | **Not triggered** |

The resulting recommendation is `benchmark_failure_explorer`: preserve the
negative paired-versus-after-only result, explain failure slices, and do not
offer an unrestricted numeric estimator. Gate C approved this form and the
memo-bound claims on 20 September 2026. Deployment, public release, or external
use requires a separately verifiable Gate D approval; this results report is
not that approval.

## Secondary same-category diagnostic

The duplicate-safe secondary diagnostic is context only. On the matched 511
rows and 31 categories that have same-category training examples, same-category
CV reached macro-category MAE `0.104396983384432`; the corresponding
category-disjoint result was `0.12249126302604002`. The observed
category-disjoint-minus-same-category gap was `0.01809427964160802`, with a
paired category-bootstrap 95% interval
`[-0.0009412969421444412, 0.03899995097197909]`.

This does not isolate a causal category-shift effect, does not replace the
primary evaluation, and does not authorize interval claims. Three singleton
category rows are excluded from the matched estimand and disclosed in the
machine report.

## Post hoc label-sensitivity check

AI-assisted visual review identified four possible image-to-mass tensions:
`lefood-0320`, `lefood-0400`, `lefood-0507`, and `lefood-0530`. They are not
declared label errors and remain in all frozen results. A clearly post hoc
sensitivity exclusion left the central direction unchanged: paired MAE
`0.1180232597071082`, after-only MAE `0.09315260329606655`, difference
`+0.02487065641104165` on 510 retained rows.

## Export evidence

The all-data M2 model uses epoch 6. Its FP32 ONNX artifact is 10,355,122 bytes,
SHA-256
`9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675`.
Maximum PyTorch/ONNX drift across the frozen parity sample was
`5.185604095458984e-06`, below `1e-4`. The exporter sidecar file SHA-256 is
`cea7f533fa53388345c5ea45828bc9d3dd20cc79a013c3c843b6f2d5f9268c54`.

The physical reference benchmark also passed. Headed Chrome `152.0.7977.83` on
an HP Laptop 15-fd0xxx (Intel i7-1355U, 15.652 GiB RAM, Windows
`10.0.22631`) used 3 warm-ups and 20 measured runs. Nearest-rank warm p50/p95
were `18.78000009059906`/`22.119999885559082` ms; peak application memory was
`45.64192485809326` MiB using
`performance.measureUserAgentSpecificMemory`; first-load body bytes were
`25,128,921`. The `1,500` ms p95 and `512` MiB memory gates both passed.
These are reference-device measurements only and support no phone or unmeasured
browser claim. At the 20 September 2026 source-freeze review, no deployment
existed; any later hosting status does not broaden the benchmark claim.

Canonical browser evidence is `reports/browser_benchmark.json`, evidence digest
`77dc5e9ee873fc453f6a081926dc2259f675c6fbf39a5e1e3e73f5053bf77be9`;
the source measurement SHA-256 is
`3c194e85724fda14550253a7994c34bd0c46026722cc80d1733767cb042a71f1`.

## Figures and interpretation

Deterministic figures are in `reports/figures/` and cover workload MAE,
paired-versus-after-only category errors, target slices, and routine robustness
deltas. Their source of truth remains the machine-readable JSON, not the SVG
labels.

The strongest supported conclusion is mixed: the learned paired representation
substantially outperforms the specified handcrafted baseline, while this compact
paired architecture does not add predictive value over the after image alone
under category shift. The wrong-pair workload replaces the after image during
both training and evaluation, so its poor result shows sensitivity to a
destructive input/target mismatch; it does not establish that the before image
adds incremental value. The single-context dataset, structured missing food
categories, possible measurement/image tensions, small category supports, and
failed uncertainty gates preclude an estimator or operational validity claim.
