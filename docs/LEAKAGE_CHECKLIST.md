# Leakage checklist

Every checked item is backed by generated artifacts, replay validation, or an
automated test. This checklist addresses information leakage; it does not imply
Gate C/D approval or field validity.

## Before modeling

- [x] Source URL/version, archive hash, workbook hash, and image inventory were
      pinned before fitting.
- [x] Targets use only the same row's recorded masses.
- [x] All exclusions remain in a ledger; no confirmatory row was deleted after
      seeing an outcome.
- [x] Exact hashes and near-duplicate connected components were computed before
      the active split.
- [x] The approved D011 amendment keeps every duplicate component
      within one outer fold.
- [x] Category sets are disjoint between every outer test fold and its
      development folds.
- [x] Active outer folds, manifest, audit, and experiment config are frozen and
      hash-bound.
- [x] The secondary same-category split was frozen before outer results, keeps
      duplicate components atomic, and is versioned separately.
- [x] Neural preprocessing and eligible M1/M2 configurations were frozen before
      outcomes.

## Features and transforms

- [x] Food name/category, filenames, masses, targets, observer score, EXIF, and
      fold identifiers are absent from neural input tensors.
- [x] Handcrafted preprocessing and Ridge alpha selection are fitted inside the
      current development boundary.
- [x] Neural normalization uses pinned pretrained constants, not statistics
      computed from outer data.
- [x] Augmentation is training-only; paired geometric transforms are shared.
- [x] Outer/test images do not enter training through augmented or cached
      tensors.
- [x] Wrong-pair maps are deterministic, self-pair-free, and fold-contained;
      the disclosed singleton fallback preserves all 514 rows.

## Selection, calibration, and execution

- [x] M1/M2 choice, Ridge alpha, epoch, early stopping, interval correction,
      and abstention threshold use only inner development evidence.
- [x] Every outer task validates the immutable run/protocol/input identities
      before execution and resume.
- [x] Outer predictions were opened once per frozen task and preserved.
- [x] Every valid row has exactly one primary outer prediction.
- [x] Final all-data M2/epoch-6 selection follows modal configuration and median
      selected epoch, not aggregate outer performance.
- [x] Export evidence cross-binds checkpoint, final selection, run, protocol,
      manifest, ONNX bytes, and parity result.

## Reporting

- [x] Metrics consume immutable prediction tables rather than live models.
- [x] Primary macro-category MAE includes all 34 valid categories, including
      singleton categories.
- [x] Bootstrap resampling preserves all observations within sampled categories.
- [x] Predefined target/support/confidence slices were computed from frozen
      outputs.
- [x] The same-category diagnostic is labeled secondary/context-only and uses a
      matched 511-row estimand for the direct comparison.
- [x] The four-row label-sensitivity analysis is explicitly post hoc, leaves the
      frozen result unchanged, and does not relabel the rows as errors.
- [x] AI-assisted visual annotations are stored separately from immutable
      `error_analysis.json` and cannot change ranking or metrics.
- [x] The public-form recommendation follows frozen gates: failed paired-value,
      numeric-demo, interval, abstention, and robustness criteria remain visible.

## Evidence identities

- Frozen results: `reports/results.json`, SHA-256
  `75d653292e34f1ad31118c5cf6249027ba3395f449bdcdeba717a94bc9444c12`.
- Bootstrap comparisons: `reports/bootstrap_comparisons.json`, SHA-256
  `07a4a5aa76da3d63147e1cd8aa0084ab8324106a8f5932f374d561f839bac3f1`.
- Same-category split ID:
  `129580d2a5560e8ad1f82ffca99bbb10e18d876a375603bbe0c3fb4b038ea1a2`.
- ONNX SHA-256:
  `9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675`.

Any future test-informed architecture, threshold, data correction, or claim
outside the frozen gate logic is exploratory v2 and must not overwrite these
artifacts.
