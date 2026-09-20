# User jobs and stories

**Current contract:** Gate C approved a benchmark and failure explorer, not a
custom-image estimator. Public deployment and Gate D remain unapproved.

## Primary job

> When I review PlateGauge, help me understand what was tested, how the paired
> model compared with alternatives, where it failed, and why the evidence does
> not support a user-facing estimator.

## Current explorer stories

| Story | Acceptance behavior |
|---|---|
| As a reviewer, I can understand the study before seeing examples | The page states the target, controlled LeFood setting, category-disjoint protocol, and selection-bias boundary |
| I can compare the intended paired model with alternatives | Aggregate values show paired MobileNet, after-only MobileNet, and baselines without obscuring that after-only performed better |
| I can inspect both close predictions and failures | Only fixed, attributed examples are selectable; representative successes and largest errors are labeled by selection rule |
| I can distinguish a benchmark record from a new estimate | Example views label the recorded target, frozen outer-fold prediction, and error; no custom files or user mass are accepted |
| I can inspect variation rather than only a headline average | Slice, category, error, and robustness summaries are available with sample/context limitations |
| I can see why product gates failed | Numeric-demo, interval-display, useful-abstention, and robustness boundaries are explained in plain language |
| I am not encouraged to operationalize the result | No scale-replacement, clinical, procurement, savings, or waste-reduction language appears |
| I can use the interface by keyboard and without color alone | Fixed-example controls, navigation, status, values, and limitations have semantic text and visible focus |

## Verification-only maintainer story

A maintainer may open the unlinked local fixed-pair benchmark harness to verify
model integrity and measure browser timing. It uses a bundled pair, suppresses
the numeric model output, accepts no custom files, and is not a public analysis
or evaluation claim.

## Other stakeholders

- A technical reviewer needs concise, evidence-backed claims and visible
  negative results.
- A researcher needs frozen manifests, split/preprocessing logic, predictions,
  metric code, and limitations to reproduce or critique the evaluation.
- A maintainer needs version hashes, static-asset boundaries, rollback
  instructions, and explicit failures rather than silent fallbacks.

## Superseded pre-outcome stories

> **Historical design only; not current behavior.** Before evaluation, the MVP
> stories included choosing a before/after pair, local input validation, a
> leftover-fraction estimate, optional conversion from starting mass, an
> empirical interval if its gate passed, and a no-number abstention state. The
> relevant gates failed, so these stories were not promoted into the current
> product and must not appear as available functionality.

## Not user stories

Custom-image inference, file upload, food recognition, calorie estimates,
clinical intake, multi-item segmentation, operational kitchen analytics,
impact dashboards, accounts, history, mobile capture coaching, uncertainty
intervals for new inputs, abstention decisions for new inputs, and automated
decisions are excluded from the Gate C-approved candidate.
