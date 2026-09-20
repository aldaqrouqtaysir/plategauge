# Public research decisions

This is the concise, release-facing decision record. It preserves the scientific
and product choices needed to interpret PlateGauge without publishing internal
project-selection work, personal planning, detailed contribution records, or
verbatim conversation history.

| Date | Decision | Evidence and consequence |
|---|---|---|
| 19 Sep 2026 | Limit v1 to standardized before/after images of one food item and container | Mixed trays, arbitrary photography, nutrition, clinical use, and operational decisions remain out of scope. |
| 19 Sep 2026 | Use only LeFood-Set v1 | It is the sole licensed v1 source. Raw data remain outside Git; source and local hashes are recorded. |
| 19 Sep 2026 | Evaluate unseen food categories with duplicate-safe nested cross-validation | Category and confirmed duplicate components are atomic. The approved pre-fit correction is bound by `reports/data_gate/fold_amendment_applied.json`; the regenerated audit has zero cross-fold duplicate components. |
| 19 Sep 2026 | Freeze the paired MobileNet hypothesis, after-only ablation, non-neural baselines, gates, and one confirmatory seed before opening outer results | Unfavorable results cannot be repaired by changing the primary model, metric, split, or threshold after evaluation. |
| 20 Sep 2026 | Preserve the paired model as the primary result after it lost to after-only | Paired macro-category MAE is `0.1227558739`; after-only is `0.0978575868`. The negative hypothesis result remains prominent. |
| 20 Sep 2026 | Use the public form `benchmark_failure_explorer` | Numeric-demo, empirical-interval, useful-abstention, and robustness gates failed. The interface therefore uses fixed examples and exposes no custom-image estimator or live numeric output. |
| 20 Sep 2026 | Treat the wrong-pair workload only as a destructive mismatch control | It substitutes another sample's after image during training and evaluation. It does not establish that the before image contributes incremental predictive value. |
| 20 Sep 2026 | Keep same-category and visual-discordance analyses secondary | Neither can replace or modify the category-disjoint confirmatory result. Reviewed image/mass tensions are not adjudicated label errors. |
| 20 Sep 2026 | Release only bounded public authorship and AI-assistance summaries | Detailed workflow, personal planning, and contribution records remain private; no unaided-implementation or independent-reproduction claim is inferred. |

## Interpretation boundary

The category-bootstrap interval is conditional on the observed 34 category
errors and the fixed folds, seed, model recipe, and predictions. It does not
measure retraining, split-selection, acquisition-site, cuisine, or deployment
uncertainty. The final all-data model is a reproducibility artifact; performance
claims come from the frozen outer predictions.

The authoritative numerical sources are `reports/results.json`,
`reports/bootstrap_comparisons.json`, and the immutable workload prediction
tables. This summary does not replace those artifacts or authorize deployment.
