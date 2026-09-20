# Preregistered evaluation protocol

**Protocol date:** 19 September 2026. At protocol freeze, outer-fold evidence
was not yet available. The confirmatory evaluation is now complete; current
outcomes are in `RESULTS.md`. Changes after an outer result was opened are
exploratory and must not overwrite this confirmatory record.

## Question and estimand

Can a compact paired-image MobileNet estimator reduce absolute error in recorded
leftover fraction for **held-out LeFood-Set categories**, compared with
after-image-only inference and handcrafted paired features?

The primary estimand is the unweighted mean of category-specific MAE values
across the 34 categories represented in the 514 audited valid pairs. Each
category therefore receives equal weight regardless of sample size.

## Splits

Use the five fixed category-disjoint outer folds in `DATA_MANIFEST.md`. For each
outer fold:

1. Keep its categories untouched.
2. Treat the other four outer folds as four grouped inner folds.
3. Train/evaluate M1 and M2 across the inner folds.
4. Select by mean inner macro-category MAE; an exact tie chooses M1.
5. Select epoch as the median of inner best epochs, using the lower integer for
   an exact half-epoch tie.
6. Refit on all four development folds for that fixed epoch.
7. Fit interval correction and abstention threshold using inner out-of-fold
   predictions only.
8. Evaluate the outer fold exactly once and append immutable predictions.

Aggregate outer predictions only after all folds finish. The final all-data
model artifact uses the modal chosen configuration—tie chooses M1—and median chosen epoch
across all five outer selections, then trains on all valid data. Its interval
correction and abstention threshold are the medians of only those inner-derived
outer-selection policies whose selected primary configuration matches that final
modal configuration. At least three of five policies must therefore contribute.
`final.json` records every included and excluded outer fold and its selected
configuration so this filtering is auditable. Neither this policy aggregation
nor the final configuration/epoch rule may inspect outer-fold metrics.

The secondary same-category five-fold analysis uses the frozen assignment in
`configs/same_category_folds_v1.json` (SHA-256
`961fc17d826bf16637d31208c0743139a5ef47548e7bc6e9a56641a4f2ae387d`,
split ID `129580d2a5560e8ad1f82ffca99bbb10e18d876a375603bbe0c3fb4b038ea1a2`).
It was generated before any outer-result artifact existed, uses seed
`20260919`, and is bound to the active manifest, protocol ID, and frozen
protocol-input hashes. It is intentionally independent of a replaceable
execution runner or source build. The validation report is
`reports/data_gate/same_category_folds_v1_validation.json` (SHA-256
`2f07288729ca49a7e16da30e105175922ec39a9415fde71845a5143097916f06`).

The assignment keeps all 504 atomic components across 514 rows intact. It
places multi-row duplicate components first while minimizing affected-category
imbalance, then assigns remaining singleton components to the least-populated
fold within their category; seed-derived hashes resolve exact ties. Every
category populates `min(5, atomic-component count)` folds. Therefore categories
`000`, `003`, `005`, `006`, `008`, `018`, `025`, `027`, and `032`, which have
fewer than five atomic components, leave unavoidable empty category-fold cells.
All other categories populate every fold. The result has total fold sizes
103/103/103/103/102, every category count range is within its largest atomic
component contribution, and no duplicate component crosses a fold. This is a
same-category diagnostic only and cannot replace the primary category-shift
result.

### Secondary diagnostic execution and estimand

The secondary diagnostic runs in a separate immutable output tree and does not
extend or rewrite the confirmatory orchestrator. For diagnostic fold `f`, it
reuses the paired-MobileNet configuration, fixed epoch, seed, preprocessing,
augmentation, and optimizer recipe selected from inner data for confirmatory
fold `f`; it changes only the training/evaluation row assignment. It does not
retune on diagnostic or outer outcomes. The fit stage is structurally unable to
open outer prediction artifacts. Only a later aggregate stage may read the five
fully validated primary paired-MobileNet outer artifacts, after all five
diagnostic prediction tasks are complete.

Three sole-category rows—categories `000`, `003`, and `025`—cannot have another
row of their category in training. Accordingly:

- the all-row 514-row/34-category result is a **mixed secondary context**, not a
  pure same-category estimate;
- the same-category estimand contains the 511 rows across 31 categories whose
  category is represented in that row's training partition; and
- the observed gap is
  `category-disjoint macro-category MAE - same-category macro-category MAE` on
  those identical 511 rows, with a 10,000-replicate paired category bootstrap
  using seed `20260919`.

A positive gap means the frozen category-disjoint protocol had higher error.
It is an observed cross-validation performance gap, not a causal estimate of
category shift: the same five fold-index recipes are reused, but an individual
sample can be evaluated under a different fold recipe across regimes. Raw
diagnostic quantiles are retained for audit only; they are not recalibrated or
used for interval-coverage, abstention, public-demo, or release-gate claims.

## Models

- Median baseline: training-fold median target.
- Handcrafted: paired RGB/HSV histograms, SSIM, edge-density change, foreground
  occupancy, and difference moments; Ridge alpha selected in inner validation.
- Primary: paired shared MobileNetV3-Small with 4-way fusion and ordered 0.05,
  0.50, 0.95 quantiles.
- Paired ResNet-50 late fusion as an architecture-family reference, not an
  exact reproduction of the associated paper or checkpoint recipe.
- After-only MobileNet with comparable head/training budget.
- Frozen paired DINOv2-S/14 representation plus fitted head.
- Wrong-pair control: sort valid rows by stable sample ID within each category
  and pair each before image with the next row's after image cyclically. The
  singleton categories `000`, `003`, and `025` cannot be deranged internally.
  For each singleton, use a deterministic same-outer-fold fallback: swap its
  assignment with the stable preimage of the first eligible after image from a
  non-singleton category in that fold. This preserves a complete 514-row
  after-image bijection, never crosses an outer fold, and creates no self-pair.
  Report the six fallback-affected rows separately and describe the control as
  within-category except for this preregistered singleton fallback.
- Observer score: contextual reference only, never called a trained baseline.
  Reproduce the associated paper's convention as consumed fraction `score / 7`;
  because PlateGauge predicts remaining fraction, map it to `1 - score / 7`.
  Preserve the compressed endpoints and label this a convention-based context
  row, not ground-truth visual measurement or a newly fitted scale.

M1 uses encoder/head learning rates `3e-5/3e-4`, dropout 0.2. M2 uses
`1e-4/1e-3`, dropout 0.4. Both use AdamW, weight decay `1e-4`, batch 32,
gradient clip 1.0, mixed precision when available, max 80 epochs, and patience
12 during inner selection. The encoder is frozen for five epochs, then only the
last two feature stages and head are unfrozen.

The median loss is Smooth-L1. Lower/upper quantiles use 0.05/0.95 pinball loss;
the exact component weights are fixed in the versioned model config before the
first confirmatory fit.

## Augmentation and preprocessing

Training only: shared geometry for both images—horizontal flip, rotation ±8°,
translation ≤5%, scale 0.95–1.05. Mild brightness/contrast may differ between
the two images. No vertical flip. Validation/test use only the frozen
resize/crop/normalization paths described below. EXIF is not an input.

All trainable 224×224 comparisons, including the ResNet reference, use the
same frozen 256-short-edge/224-center-crop pipeline so the comparison does not
change both architecture and crop at once. The pinned ResNet checkpoint declares
`crop_pct=0.95`, rather than MobileNet's `0.875`; this deliberate shared-input
choice is disclosed and means the ResNet row is not a best-case checkpoint
benchmark. Frozen DINOv2 remains the predeclared exception and uses its native
518×518 deterministic transform.

## Metrics

Primary: macro-category MAE.

Secondary: micro MAE, RMSE, signed bias, median and 90th-percentile absolute
error, Spearman correlation, and fractions within ±0.10 and ±0.20. Report exact
zero, `(0,.25]`, `(.25,.50]`, `(.50,.75]`, `(.75,1)`, and exact one target
slices; category-support, before-mass, observer, and interval-width slices; and
model size, load bytes, memory, warm browser p50/p95 latency.

Undefined metrics (for example correlation in a constant slice) remain missing
with a reason; they are not coerced to zero.

## Empirical intervals and abstention

Correct raw quantile intervals using nonnegative lower/upper residual additions
derived only from inner out-of-fold predictions. Bound corrected endpoints to
`[0,1]`. These are called empirical benchmark intervals because calibration and
test categories differ; no conformal coverage guarantee is claimed.

For each outer fold, abstain when corrected width exceeds
`min(0.30, inner-OOF 80th percentile width)`. Evaluate coverage, width, risk,
retention, and slice retention on untouched outer data. Public display and claim
gates are defined in `SUCCESS_METRICS.md`.

## Statistical inference

- Paired category-level bootstrap: 10,000 replicates, sample 34 categories with
  replacement, preserve all observations within each sampled category, and
  calculate paired metric differences with 95% percentile intervals.
- Paired sign-flip test: apply to 34 category-level MAE differences against
  predefined comparisons; use exact enumeration when feasible or a fixed-seed
  Monte Carlo approximation otherwise; Holm-adjust this secondary family.
- Report effect sizes and intervals. P-values do not select the headline claim.

The confirmatory seed is `20260919`. Seeds `20260920` and `20260921` may be used
for a labeled stability analysis only if total GPU use remains below ten hours.

## Robustness and errors

After model freeze, test shared ±5° rotation/translation/crop, JPEG quality 50,
brightness/contrast ±20%, Gaussian blur σ=1, and independent after-only
brightness/blur/translation. Test same-image, swapped-order, and unrelated-pair
misuse. Report absolute metric delta; do not tune on these outcomes.

Inspect the twenty largest primary-model errors with source images available
locally. Use predefined tags—oil/sauce residue, rice/porridge versus background,
glare, misalignment, cropping, boundary target—and add a new tag only with a
definition. Do not publish private annotations or unlicensed images.

## Frozen decision rules

The data, model-value, interval, abstention, efficiency, numeric-demo,
benchmark-only, robustness, quantization, and stop thresholds in
`SUCCESS_METRICS.md` and `KILL_CRITERIA.md` control interpretation. A missed
threshold is not repaired through post-hoc exclusions or metric substitution.
