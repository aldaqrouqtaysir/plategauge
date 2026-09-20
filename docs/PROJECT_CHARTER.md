# PlateGauge project charter

**Source-freeze snapshot (20 September 2026):** Gate B had authorized
implementation, and Gate C approved PlateGauge only as a **benchmark and
failure explorer**, subject to the Gate C review memo's claim boundaries. At
this checkpoint Gate C had not authorized public deployment, a release tag, or
Gate D.

## Current one-sentence purpose

PlateGauge is a static research-evidence explorer that explains how paired and
after-only vision models behaved on a frozen, category-disjoint LeFood-Set v1
benchmark, including representative successes, large errors, slice results,
and limitations.

## Evidence of need

The [UNEP Food Waste Index Report
2024](https://www.unep.org/resources/publication/food-waste-index-report-2024)
describes measurement as part of understanding food waste, and the UAE
[ne'ma initiative](https://www.nema.ae/en/baseline/faqs) establishes a relevant
national food-loss-and-waste context. These sources justify studying
measurement methods. They do not establish that PlateGauge is operationally
useful or that it reduces waste.

## Current audience and product contract

The intended audience is a technical reviewer, researcher, or food-service
analyst examining the frozen study and its failure modes. The Gate C-approved
candidate:

- presents aggregate model comparisons, error and slice views, and a curated
  set of fixed, attributed LeFood examples;
- accepts no arbitrary images or user-supplied mass;
- produces no new per-user prediction, remaining-mass result, empirical
  interval, or abstention decision; and
- may expose an unlinked local fixed-pair harness solely to verify browser
  inference and timing. That harness uses a bundled pair, suppresses the model's
  numeric output, and is not evaluation evidence.

The explorer does not represent ordinary consumer photography, mixed meals,
buffets, regional cuisine, clinical patient monitoring, or institutional
deployment.

## Research hypothesis and outcome

The preregistered hypothesis was that a compact shared encoder using correctly
paired before/after images would achieve lower category-macro MAE than both
handcrafted paired features and an after-image-only neural ablation on held-out
food categories.

The frozen result did not support the full hypothesis. The paired MobileNet
beat the handcrafted Ridge baseline but was worse than the after-only MobileNet
by `0.024898287038787673` macro-category MAE; the paired category-bootstrap 95%
interval for that difference was
`[0.007664708956515841, 0.043684385882585365]`. The public numeric-demo,
interval-display, and useful-abstention gates also failed. Those negative
results are the reason the current contract is a benchmark/failure explorer.

## Current explorer journey

1. A visitor reads the study question, acquisition boundary, and frozen
   protocol.
2. The visitor compares paired, after-only, and baseline aggregate results.
3. The visitor selects among fixed, attributed examples spanning close
   predictions and large errors.
4. The explorer shows the recorded target, frozen prediction, error, and a
   bounded interpretation of that specific benchmark record.
5. The visitor reviews slice, robustness, selection-bias, and non-use
   limitations. No custom input or new decision is produced.

## Frozen method and comparisons

- Primary model: shared MobileNetV3-Small encoder with pair fusion and an
  ordered 5th/50th/95th quantile head.
- Simple baselines: training-fold median and handcrafted image-change features
  with Ridge.
- Neural comparisons: paired ResNet-50, after-only MobileNet, frozen paired
  DINOv2-S/14, and fixed wrong pairing. The wrong-pair control uses stable
  within-category cycles where possible and the frozen same-outer-fold
  bijective swap fallback documented in `EVALUATION_PROTOCOL.md` for the three
  singleton categories.
- Primary evaluation: nested five-fold category-disjoint cross-validation on
  514 valid pairs across 34 categories, summarized by macro-category MAE.

## Superseded pre-outcome estimator design

> **Historical design only; not the current product contract.** Before the
> frozen results were known, the preregistered MVP contemplated user-selected
> before/after files, local ONNX inference, optional starting mass, an empirical
> interval if its gate passed, and a no-number abstention state. The required
> evidence gates did not pass. That interface is not exposed by the current
> candidate and must not be described as an available PlateGauge feature.

The low-level estimator types and tests may remain in the repository as part of
the preregistered research implementation and audit trail. Presentation code
must not use them to bypass the Gate C outcome.

## Release boundary

The implementation is a local static React/TypeScript candidate. A future
approved release could be served from GitHub Pages, but no deployment or Gate D
approval exists. The current browser candidate uses only same-origin static
assets and has no app server, account, database, telemetry, user-image route,
or paid API.

## Allowed claims

Only claims listed as supported in `CLAIM_EVIDENCE_MAP.csv` may be published.
Every metric claim must identify LeFood-Set v1 and the frozen protocol when
omission would imply broader validity. The negative paired-versus-after-only
finding and failed product gates must remain visible.

## Prohibited claims

No custom-image estimation, useful interval/abstention, “first,”
state-of-the-art, production-ready, clinical, UAE-valid, cuisine-wide,
smartphone-valid, scale-replacement, waste-reduction, cost-saving, endorsement,
or outcome-guarantee claim. No statement that a named contributor independently
performed AI-generated work they did not review and understand.

## Stop conditions

Do not release if evidence integrity is broken, required attribution is
missing, fixed examples or displayed metrics diverge from the frozen records,
the static candidate creates an undisclosed data flow, or public language
implies an estimator or real-world impact. `KILL_CRITERIA.md` remains
controlling for the research evidence.
