# User-testing decision

**Current contract:** Gate C approved PlateGauge as a static benchmark/failure
explorer. It accepts no custom images and provides no new per-user estimate,
interval, or abstention decision. Gate D and deployment remain unapproved.

## Decision for v1

No user test is required for the v1 release candidate.

1. The central technical question—how the models perform against recorded mass
   ratios under the frozen protocol—was answered by the automated benchmark.
2. The current explorer makes no usability, adoption, behavior-change,
   savings, waste-reduction, or operational-utility claim.
3. Accessibility and static-data-flow claims are supported only to the extent
   covered by the recorded automated/browser tests; no broader user-validation
   claim will be made.
4. Qualified institutional food-service or audit participants are not reliably
   available, and convenience testers could not validate model accuracy.
5. Making informal testing a release blocker would add activity without
   strengthening any authorized claim.

This is not a claim that the explorer is user-validated. `USER_TEST_RESULTS.md`
must remain “not conducted” unless genuine testing occurs.

## Optional post-v1 comprehension study

This study is optional, not a Gate D blocker. Proceed only if three qualified
food-service, food-audit, research, or technical-review participants become
available and the maintainer approves.

### Important question it would answer

Can an intended reader correctly distinguish a fixed benchmark record from a
new estimate, explain the negative paired-versus-after-only result, and identify
the explorer's major scope and evidence limitations?

### Why automation cannot answer it

Automated checks can verify text, values, keyboard behavior, and the absence of
an upload route. They cannot establish whether a person interprets the fixed
examples, failed gates, and limitation language as intended.

### Minimum viable process and time

- Three participants, ten minutes each.
- Maintainer coordination and observation: under one hour total.
- No participant images, annotation, survey recruitment campaign, or sensitive
  work information.
- Record only task completion, interpretation answers, confusion tags, and
  suggested wording; report results in aggregate without public names or email
  addresses.
- Participation is voluntary, with no promised compensation, and may stop at
  any time.

### Ten-minute script

1. Ask the participant to state what the explorer does before opening an
   example.
2. Show one fixed close-prediction record and one fixed large-error record; ask
   whether either is a new estimate for the participant.
3. Ask which model performed better on the primary metric and what the result
   does—and does not—show about paired images.
4. Ask why the numeric-demo, interval, and useful-abstention gates did not
   authorize an estimator.
5. Ask for two important limitations and the single most confusing phrase or
   interaction.

### Interpretation rule

The study would support only a narrow comprehension statement if all three
participants correctly identify the fixed-record nature of the examples, the
direction of the paired-versus-after-only finding, the absence of custom-image
inference, and at least two scope limitations. A weaker result changes wording,
navigation, or explanation only; it cannot modify the frozen model result or
justify an estimator, interval, abstention, operational, or impact claim.
