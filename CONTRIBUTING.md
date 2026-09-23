# Contributing

PlateGauge is in a time-bounded research-release phase. Small,
evidence-improving contributions are welcome; feature expansion is not.

## Before opening a change

1. Read `docs/SCOPE_AND_NON_GOALS.md`, `docs/EVALUATION_PROTOCOL.md`, and
   `docs/ETHICS_PRIVACY_SAFETY.md`.
2. Open an issue describing the failure, evidence, and proposed acceptance
   test. Do not include private photographs or raw LeFood-Set files.
3. Do not change the frozen split, target, primary metric, outer-fold results,
   or release claim thresholds after evaluation begins. A scientifically
   necessary change must be labeled exploratory and documented in the
   public research-decision record and versioned release notes.

## Development expectations

- Keep raw data and generated checkpoints out of Git unless a release process
  explicitly licenses and inventories an artifact.
- Add tests for behavior changes and keep code deterministic where practical.
- Follow the pinned setup and scoped checks in the
  [development guide](docs/DEVELOPMENT.md). It separates browser development,
  synthetic monitoring tests, and frozen-evidence verification from research
  reproduction; none of these instructions calls for a new training run.
- Do not add telemetry, external image uploads, accounts, medical or nutrition
  claims, or server-side processing.
- Record third-party licenses for every new dataset, model, or dependency.
- Use plain, calibrated language. Do not add unverified performance or impact
  claims to public material.

## Research integrity

Test outcomes must not be deleted because they are unfavorable. Report changes
to exclusions, preprocessing, metrics, or thresholds before rerunning final
evaluation. Contributions made with substantial AI assistance should say what
was generated and how it was reviewed.

By contributing, you agree that your code contribution may be distributed
under Apache-2.0 and that you have the right to submit it. This does not apply
to third-party data or assets.
