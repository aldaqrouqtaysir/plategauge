# PlateGauge

PlateGauge is a category-shift computer-vision benchmark and failure explorer
for research on estimating the fraction of a **single food item** remaining
from standardized before-and-after photographs. The intended acquisition
setting is deliberately narrow: the same item and container, photographed from
a comparable angle, distance, and lighting.

> **Evidence and release boundary:** Gate C selected the **benchmark and failure
> explorer** form on 20 September 2026; it did not authorize an unrestricted
> numeric estimator. A checkout is authorized for release only when its
> `v1.0.0` tag contains a verified `release/gate-d-approval.json` approval child
> and the fail-closed release pipeline passes. If that approval record is absent
> or invalid, or any release check fails, deployment is blocked.

![PlateGauge benchmark and failure explorer](reports/media/01-question-and-boundary.png)

New reviewers can use the [five-minute reviewer quickstart](docs/REVIEWER_QUICKSTART.md)
to verify the outcome, evidence boundary, and fixed-example explorer without
downloading the raw dataset or retraining a model.

## At a glance

| Item | Evidence-bound summary |
|---|---|
| Public form | Fixed-example benchmark and failure explorer; no visitor uploads or new numeric estimates |
| Data | 514 valid LeFood-Set v1 pairs across categories `000`-`033`; all 154 workbook rows in categories `034`-`049` lack archived image pairs and are outside the benchmark |
| Primary finding | Paired MobileNet MAE `0.1228`; after-only MobileNet MAE `0.0979` |
| Decision | The paired-image advantage did not appear; estimator, interval, abstention, and robustness claims are blocked |
| Engineering | 10.36 MB FP32 ONNX; local production bundle and real-model browser smoke passed |
| Main limitation | One controlled Indonesian hospital acquisition context; no field or operational validity claim |

Exact precision, hashes, statistical intervals, and gate calculations remain in
the [machine-readable results](reports/results.json) and linked evidence files.

## What the evaluation found

The confirmatory experiment evaluated all 514 valid LeFood-Set v1 pairs across
34 held-out food categories. The paired MobileNet reached macro-category MAE
`0.1228`; the after-image-only MobileNet reached `0.0979`. The
paired-minus-after-only difference was `+0.0249` (paired category-bootstrap 95%
interval `[0.0077, 0.0437]`). In this protocol, adding the before image did not
improve the compact model. That interval resamples the 34 observed category
errors while holding the frozen folds, seed, trained predictions, and model
recipe fixed; it is not uncertainty over retraining, alternative splits, or a
real-world food population.

The paired model did beat the best non-neural baseline, handcrafted Ridge:
`0.1228` versus `0.2515` macro-category MAE. That is a
useful representation-learning result, but it does not rescue the paired-value
or public-estimator hypotheses.

The target distribution is endpoint-heavy: 207/514 records are exact zero and
47/514 are exact one, so 254/514 (`49.4%`) sit at a boundary. The broad interior
slices have materially higher error; the endpoint prevalence must remain visible
beside aggregate metrics.

| Frozen gate | Outcome |
|---|---|
| Paired value over after-only and non-neural baselines | **Failed** because paired was worse than after-only |
| Public numeric demo | **Failed**: macro MAE `0.122756`, P90 error `0.381611`, worst broad-slice MAE `0.274511` |
| Empirical interval display | **Failed**: coverage `0.931907`, but mean width `0.667206` |
| Useful-abstention claim | **Failed**: only `0.252918` retained overall and minimum slice retention was `0.021277` |
| Efficiency | **Passed**: 10,355,122-byte FP32 ONNX; PyTorch/ONNX drift `5.1856e-06`; DINO gap `0.0194952` |
| Project stop | **Not triggered** |

These are benchmark-specific findings, not evidence of operational food-waste
measurement, field robustness, or impact. See [the full results](docs/RESULTS.md),
[error analysis](docs/ERROR_ANALYSIS.md), and
[robustness report](docs/ROBUSTNESS.md).

## Intended research system

```text
before image + after image
          |
          v
local validation and deterministic preprocessing
          |
          v
shared MobileNetV3-Small encoder + paired feature fusion
          |
          v
ordered low / median / high quantile outputs
```

The research target is:

```text
leftover_fraction = recorded_weight_after / recorded_weight_before
```

The originally planned product would show a numeric result only if the frozen
gates passed. They did not. The benchmark-only interface explains the protocol,
comparisons, slices, and failures without presenting the paired model as a
reliable user-facing estimator. The Gate C decision selected this form.
Release builds suppress numeric estimates, failed intervals, and unsupported
abstention claims; authorization is governed by the machine-verifiable condition
above.

## Scope boundaries

PlateGauge does **not** identify food, estimate nutrition, make clinical
decisions, replace a scale, or claim to reduce food waste. It is not validated
for arbitrary meals, buffet trays, hospitals, UAE cuisine, smartphone use, or
uncontrolled photography. The only source dataset is one controlled Indonesian
hospital acquisition context.

## Evaluation design

The primary design uses duplicate-safe, category-disjoint nested
cross-validation on [LeFood-Set v1](https://data.mendeley.com/datasets/cchsk79jkt/1).
It includes median and handcrafted baselines, an after-only ablation, and a
destructive mismatch control that substitutes another sample's after image.
That mismatch control does not isolate the incremental value of the before
image. The study also includes paired ResNet-50 and DINOv2 references, frozen
acceptance rules, category-level statistics, a secondary same-category
diagnostic, robustness perturbations, and post hoc error review. The protocol is in
[docs/EVALUATION_PROTOCOL.md](docs/EVALUATION_PROTOCOL.md).

The secondary matched diagnostic found macro-category MAE `0.1044` under
same-category folds versus `0.1225` under category-disjoint folds on the same
511 rows and 31 categories. The observed gap was `0.0181`, with a bootstrap
interval crossing zero. This is context, not a causal estimate and not a
substitute for the primary result.

## Privacy and software status

The browser architecture uses local WASM inference with no account, history,
analytics, application database, or image-upload API. Automated tests cover the
local processing boundary and the exact production bundle. On the HP reference
laptop in headed Chrome
152.0.7977.83, the frozen benchmark recorded warm p50/p95 inference of
`18.78000009059906`/`22.119999885559082` ms, 45.64192485809326 MiB peak
application memory, and 25,128,921 first-load body bytes; all browser gates
passed. These measurements support only that exact reference environment, not
phones or unmeasured browsers. Repository contents alone do not assert a live
deployment; release state is determined by the approval record and pipeline
condition above.

## Repository map

```text
src/plategauge/       Python data, models, training, evaluation, and export
web/                  React/TypeScript browser application
configs/              frozen configuration files
data/                 manifests and local ignored data
tests/                Python, web, browser, privacy, and security tests
reports/              immutable machine-readable evidence and figures
docs/                 public research, governance, and release records
.github/workflows/    CI and release automation
```

Raw LeFood-Set files are excluded from version control. Reproduction and rights
details are in [the data manifest](docs/DATA_MANIFEST.md),
[datasheet](docs/DATASHEET.md), and [data licenses](docs/DATA_LICENSES.md).

## Project records

- [Results](docs/RESULTS.md)
- [Model card](docs/MODEL_CARD.md)
- [System card](docs/SYSTEM_CARD.md)
- [Claim-evidence map](docs/CLAIM_EVIDENCE_MAP.csv)
- [Research decisions](docs/RESEARCH_DECISIONS.md)
- [Five-minute reviewer quickstart](docs/REVIEWER_QUICKSTART.md)
- [Cross-platform reproducibility note](docs/REPRODUCIBILITY_NOTE.md)
- [Public AI-assistance disclosure](docs/AI_ASSISTANCE_PUBLIC.md)
- [Authorship and contribution boundary](docs/AUTHORSHIP.md)

## Attribution, license, and authorship

PlateGauge source code is licensed under the [Apache License 2.0](LICENSE).
LeFood-Set v1 is CC BY 4.0; the trained artifact is dataset-derived and must
retain attribution and change notices. See [NOTICE](NOTICE).

This is a substantially AI-assisted project. Taysir Al Daqrouq set the
objectives and constraints, approved the protocol and duplicate-safe fold
amendment, reviewed the frozen evidence—including the negative paired-model
result—and selected the benchmark/failure-explorer form and claim boundaries.
The public authorship and AI-assistance records summarize those boundaries;
more detailed private workflow records are deliberately not part of the public
tree. Gate C approval alone is not evidence of independent unaided
implementation or independent technical reproduction. Release authorization
follows the machine-verifiable condition above.
