# Scope and non-goals

**Controlling scope:** Gate C approved PlateGauge as a benchmark/failure
explorer. It did not approve deployment, Gate D, or an unrestricted estimator.

## Current product scope

- Static explanation of the LeFood-Set v1 study and its controlled acquisition
  assumptions.
- Aggregate comparison of the paired MobileNet, after-only ablation, and frozen
  baselines under the category-disjoint protocol.
- Error, category/slice, and robustness views that retain relevant support and
  selection-bias limitations.
- Fixed, attributed benchmark examples showing recorded targets, frozen
  outer-fold predictions, and absolute errors.
- Explicit presentation of failed paired-value, numeric-demo,
  interval-display, useful-abstention, and robustness-claim gates.
- Accessibility, privacy, security, reproducibility, attribution, and
  claim-governance documentation for the static candidate.
- An unlinked local fixed-pair harness for artifact integrity and browser timing
  only. Its numeric output is suppressed and it is not evaluation evidence.

## Research-method scope

- A paired model for one before and one after image of the same single food and
  container under controlled, comparable capture conditions.
- The frozen target `weight_after / weight_before` and ordered quantile outputs
  as evaluated research objects.
- LeFood-Set v1 category-shift evaluation, baselines, ablations, error analysis,
  perturbations, latency, model size, and memory.

This method scope describes what was studied. It does not authorize fresh
predictions or convert the explorer into a measurement tool.

## Explicitly out of scope for the current candidate

- Arbitrary image selection or upload, camera capture, live video, or remote
  inference.
- Any new per-user leftover-fraction or remaining-mass estimate.
- Any public empirical interval or abstention/quality decision for a new input.
- Multiple foods or trays; buffets; arbitrary phone viewpoints.
- Food identification, segmentation as a public output, ingredients, calories,
  nutrition, allergens, diet advice, or meal recommendations.
- Clinical intake monitoring, patient care, or any medical use.
- Procurement, billing, compliance, or automated operational decisions.
- Claims of generalization to UAE food, Indonesian hospitals beyond the source
  sample, other cuisines, homes, restaurants, or phones.
- Accounts, user-data history, backend inference, analytics, advertising,
  cookies, third-party scripts, or a database.
- Realized food-waste, cost, emissions, or behavior-change impact.
- New data collection or manual labeling for v1.

## Superseded pre-outcome product scope

> **Historical design only.** The preregistered plan allowed a local browser
> workflow with two user-selected images, a bounded fraction, a gated empirical
> interval, uncertainty-based abstention, and optional remaining grams from a
> user-supplied starting mass. The frozen product gates failed. None of those
> outputs is part of the current explorer, even though research code and tests
> remain for auditability.

## Scope-change rule

Only correctness, accessibility, privacy, security, broken-link, attribution,
or evidence-integrity fixes are permitted while preparing the Gate D review.
Any custom-input estimator, new model, dataset, feature, or protocol is a
separately labeled future experiment and cannot alter the confirmatory v1
claims. Public deployment requires explicit Gate D approval.
