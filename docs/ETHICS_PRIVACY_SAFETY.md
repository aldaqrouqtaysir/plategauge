# Ethics, privacy, fairness, and safety review

**Source-freeze snapshot (20 September 2026):** Gate C had approved a benchmark
and failure explorer only. Deployment and Gate D approval had not occurred at
this checkpoint; the candidate accepted no custom images and provided no new
estimates.

## Intended benefit and evidence boundary

PlateGauge studies a controlled leftover-fraction prediction problem and makes
its negative and positive benchmark findings inspectable. The current value is
research transparency: reviewers can compare models, examine fixed failures,
and see why the evidence did not support an estimator product.

The study cannot show that PlateGauge changes behavior, saves money, reduces
waste, works in an institution, or benefits a specific community. It also does
not establish paired-image value over after-only inference: the paired
MobileNet was worse on the frozen primary metric.

## Privacy design for the current explorer

- The visible candidate is composed of same-origin static assets and accepts no
  arbitrary files, camera input, mass input, account data, or free text.
- It bundles only fixed LeFood examples selected from the licensed research
  dataset, with attribution and change notices. These are evidence records, not
  visitor data.
- There is no app server, application database, analytics, advertising,
  cookies, telemetry, user history, or prediction collection.
- The unlinked local benchmark harness loads one bundled fixed pair and the
  same-origin model for timing/integrity checks. It suppresses and does not
  retain the numeric output.
- Automated production-route tests restrict network traffic to the enumerated
  static assets. No user-image or prediction endpoint exists.
- A future GitHub Pages host could process ordinary request metadata. The
  explorer cannot promise anonymous browsing or control the visitor's browser,
  extensions, device software, network, or hosting provider.

## Safety and misuse

The main current risks are mistaking frozen examples for fresh estimates,
cherry-picking the close examples, hiding negative results, or extending a
controlled benchmark into clinical or operational decisions. Controls include:

- labeling examples as fixed benchmark records and explaining their selection
  rules;
- showing representative close predictions alongside the largest errors;
- foregrounding the paired-versus-after-only result and failed product gates;
- providing no custom-input route, per-user number, remaining-mass result,
  public interval, or abstention decision;
- prohibiting calories, nutrition, diagnosis, patient monitoring,
  procurement, billing, compliance, and scale-replacement claims; and
- exposing no automatic action or downstream decision API.

## Superseded pre-outcome safety design

> **Historical design only; not current behavior.** The preregistered estimator
> included file validation, finite/bounds checks, empirical interval gating,
> and a no-number abstention state. Because the numeric-demo, interval, and
> useful-abstention gates failed, those controls were not used to justify a
> public estimator. Retained implementation/tests form part of the research
> audit trail, not an available visitor workflow.

## Fairness and selection bias

No demographic attribute or individual person is part of the model, so a
demographic fairness claim would be inappropriate. Relevant performance
differences are examined by food category, category support, visual
texture/failure theme, observer level, before-mass quintile, and target range.
Uncertainty-width slices are analysis artifacts, not a public interval or
abstention claim.

The strongest fairness/external-validity limitation is sampling: one controlled
Indonesian hospital acquisition context does not represent foods or capture
conditions elsewhere. “Fair across cuisines” and “works for UAE food” are
prohibited claims.

## Environmental and resource considerations

Training used a compact transfer-learning model and a predefined two-option
configuration search. Extra seeds were bounded by the project compute budget.
The candidate is static and requires no per-visitor cloud inference; the model
runs only in the optional local fixed-pair timing harness. These are design
facts, not a measured carbon-reduction claim.

## Human oversight and authorship

A reviewer must interpret every result within the frozen dataset and protocol.
The named maintainer remains responsible for reviewing evidence, contribution wording,
and public claims. Neither responsibility is delegated to the model or to the
AI-assisted implementation workflow.

## Release blockers

- Presence of any custom-input route, new numeric estimate, interval,
  remaining-mass value, or abstention decision.
- Fixed examples, displayed metrics, or selection labels diverge from the
  frozen evidence.
- Public material implies paired-image superiority, operational/clinical
  validity, scale replacement, or realized impact.
- Required dataset/model attribution is missing.
- A static route creates an undisclosed data flow or third-party dependency.
- Gate D is absent or is inferred from Gate C approval.
