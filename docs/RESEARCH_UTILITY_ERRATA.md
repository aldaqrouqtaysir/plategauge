# Research utility audit and prospective corrections

Audit date: 23 September 2026. Baseline reviewed:
`cb3a3b310658eb25d5cf94c0aa118b3ae4446ef2`.

These are implementation corrections and synthetic contract tests, not a new
experiment. No data, folds, model, frozen predictions, scientific metrics,
calibration artifact or release evidence has been changed. The failed interval
and useful-abstention gates remain failed. No public uncertainty interval or
coverage guarantee is introduced.

## Empirical residual quantile: explicit versioning

The historical function used
`quantile(scores, min(1, ceil((n + 1) * coverage) / n), method="higher")`.
NumPy's `higher` interpolation selects an index on its `(n - 1)` grid. It can
therefore select the next larger order statistic, rather than exactly the
one-based rank `min(n, ceil((n + 1) * coverage))`. For scores `0, …, 19` and
coverage `0.90`, the historical result is `19`; the rank-19 result is `18`.
The discrepancy is conservative in score size, not evidence of undercoverage
or a demonstrated improvement in the model.

The prospective API distinguishes two strategies:

- `legacy_numpy_higher_v1` is the **default** of both
  `finite_sample_quantile` and `interval_correction`. It retains the historical
  numerical recipe exactly, including the behavior above.
- `finite_rank_v2` is an **explicit opt-in** that selects the clipped one-based
  rank directly. It is covered by synthetic tests only and is not enabled in
  frozen orchestration, model export, the website or any research result.

Existing orchestration calls omit the strategy argument and continue to use
the legacy default. A future scientific use of v2 must name the strategy in a
new, separately versioned protocol before evaluation; it must not overwrite or
silently recalibrate historical results. Neither strategy creates a conformal
guarantee across new categories or acquisition settings. The original code
revision and source-hash-bound runner remain the authority for reproducing the
historical run. Maintenance source changes produce a different runner
fingerprint; historical run identities and source hashes must not be rewritten
to disguise that difference.

The interval helpers now reject nonfinite bounds, empty arrays and
broadcast-mismatched bounds. Valid finite legacy inputs retain their numerical
behavior. Invalid width/retention parameters now fail explicitly.

## ONNX parity: fail closed on invalid comparisons

The former `assert_onnx_parity` comparison alone could accept a NaN drift or a
NaN tolerance, because `NaN > tolerance` is false. The lower-level drift
calculation could also broadcast unequal output shapes before subtraction.
The corrected utilities require finite, matching `[batch, 3, 224, 224]` inputs,
finite exact `[batch, 3]` outputs, and finite nonnegative tolerance and drift.
Valid float32 comparisons retain the original subtraction and drift value.

Both the generic `scripts/export_model.py` path and the guarded frozen exporter
use these parity utilities. The canonical `compose_export_evidence` already
rejected nonfinite drift independently, and the published artifact records a
finite maximum drift of `5.185604095458984e-06`. The audit does **not** establish
a defect in the released ONNX model and does not re-export or replace it.

The generic export CLI also previously used 15 MiB (15,728,640 bytes) instead
of the canonical decimal 15 MB ceiling. It now imports the frozen exporter's
existing `15_000_000`-byte constant. Mocked CLI tests cover one byte below the
limit, the exact limit, one byte above it and the former MiB limit, without
loading or exporting a model. The released model is 10,355,122 bytes and is
unaffected. Current tooling documentation now uses the same decimal units.

## Verification and remaining evidence limits

The regression tests use synthetic arrays and mocked runtimes; they perform no
model fitting, research calibration or real-data inference. Legacy numerical
equivalence is checked across sample sizes including 411 and 412 and several
coverage levels; v2 is checked for exact rank, ties and boundary sample sizes.
Nonfinite, empty, invalid-parameter and broadcast-shape cases fail closed.

The audit separately recomputed the existing paired and after-only
macro-category MAEs from committed predictions and confirmed the unchanged
values in [Results](RESULTS.md). The existing abstention policy retains 130
observations from only 18 of 34 categories. Its reported retained macro-MAE
therefore averages a different category set from the full macro-MAE; the
reported reduction is not evidence of within-category improvement everywhere.
The existing failure decision is unchanged. A future protocol should report
category retention and matched-category risk alongside slice retention.

The 130/18 counts above are an audit-derived inventory of retained rows and
distinct categories, not a new accuracy result. They use the unchanged
`q95 - q05 <= 0.30 + 1e-12` policy in the committed
[results record](../reports/results.json) on the primary prediction tables for
[fold 0](../reports/experiments/confirmatory/tasks/outer.fold-0.paired_mobilenet/workload/predictions.csv),
[fold 1](../reports/experiments/confirmatory/tasks/outer.fold-1.paired_mobilenet/workload/predictions.csv),
[fold 2](../reports/experiments/confirmatory/tasks/outer.fold-2.paired_mobilenet/workload/predictions.csv),
[fold 3](../reports/experiments/confirmatory/tasks/outer.fold-3.paired_mobilenet/workload/predictions.csv), and
[fold 4](../reports/experiments/confirmatory/tasks/outer.fold-4.paired_mobilenet/workload/predictions.csv).

This maintenance does not supply independent camera-photo accuracy validation,
physical-device camera testing, retraining-stability evidence or operational
impact. Those require new evidence, not additional utility tests. See the
[model card](MODEL_CARD.md), [results](RESULTS.md), and
[camera system card](CAMERA_SYSTEM_CARD.md) for the existing boundaries.
