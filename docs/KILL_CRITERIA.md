# Kill, downgrade, and fallback criteria

These rules prevent schedule pressure from turning a failed experiment into an
inflated public claim.

## Stop the PlateGauge direction

Stop model/product expansion and return to Gate A with PDF OCR reliability
triage as the standing fallback if any of the following cannot be corrected
before opening outer results:

- Fewer than 500 valid paired observations remain.
- LeFood-Set licensing changes or cannot support the intended use.
- Workbook-to-image pairing or recorded-mass semantics cannot be established.
- Duplicate containment or category-disjoint evaluation cannot be guaranteed.
- Privacy-by-design cannot be implemented without uploading images.

Stop the public model after frozen evaluation if:

- Macro-category MAE is greater than 0.20.
- The paired model fails to beat both the median and handcrafted baselines.
- Evaluation was contaminated and cannot be rerun from an untouched protocol.
- A material numerical or licensing claim cannot be traced to evidence.

## Downgrade to a benchmark/failure explorer

Do not publish an unrestricted numeric estimator when:

- Macro-category MAE lies in `(0.10, 0.15]`.
- The paired improvement confidence interval includes no improvement.
- Any broad target-slice MAE exceeds 0.15.

The explorer may show frozen predictions, baseline comparisons, errors, and
limitations, but it must not invite users to treat arbitrary uploaded images as
validated estimates.

## Publish only a negative research record

If macro-category MAE lies in `(0.15, 0.20]`, publish no upload-based estimator
or benchmark explorer that could be mistaken for a usable measurement tool.
Preserve the reproducible protocol, frozen aggregate results, failure analysis,
and lessons learned as a clearly negative research result. Exactly `0.20`
belongs to this range; only a result greater than `0.20` triggers the numerical
project-stop threshold above. Other fatal rules can still stop publication.

## Remove optional claims/features

- Hide empirical intervals if coverage is outside 85–95%, mean width exceeds
  0.30, or any broad target slice is below 80% coverage. Interval-gate failure
  alone does not downgrade a point estimator that passes every separate public
  numeric-demo and paired-value rule.
- Do not call abstention useful unless it reduces macro-category MAE by at least
  20% at about 80% retention and retains at least 50% of each broad target slice.
- Do not claim routine-perturbation robustness when any predefined perturbation
  increases macro-category MAE by more than 0.03; narrow capture guidance.
- Do not ship UINT8 unless relative MAE degradation is ≤2% and measured latency
  improves ≥10%.
- Do not make the compact-efficiency comparison if MobileNet is more than 0.02
  macro-MAE worse than DINOv2.
- Do not claim browser performance beyond the exact tested hardware/browser.

## Version-freeze stop

After the v1 evidence freeze, add no feature and change no confirmatory result
or core claim. If the project cannot satisfy its honest release form, preserve
the strongest audited artifact instead of weakening a gate or inflating a
claim. Any later model, dataset, protocol, or threshold change is a separately
preregistered exploratory version.

## Decision authority

The system recommends the evidence-consistent path. The named maintainer
approves Gate C and Gate D public language. Approval cannot override a fatal
legal, privacy, or evaluation-integrity failure.
