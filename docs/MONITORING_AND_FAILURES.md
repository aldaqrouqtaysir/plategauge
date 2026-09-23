# Monitoring, incidents, and failure handling

## Current live profile — 23 September 2026

The active profile is `camera-experimental-r3`. Its
[deployment/live check 35893477387](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35893477387)
and [weekly smoke 35894343530](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35894343530)
passed: the exact 45-file inventory and six generated-input browser/harness checks
were verified. [Source CI 35893340197](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35893340197)
passed after a source-only legacy test-caption correction; the deployed archive
was unchanged. The active weekly workflow is `weekly-camera-r3-smoke.yml`, on
Mondays at 05:37 UTC. Earlier camera profiles and the benchmark-root smoke remain
inactive while r3 is selected.

Documentation monitoring is independent. Its latest recorded
[run 35857323362](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35857323362)
failed with 163/164 links successful and one MDPI HTTP 403. That is an unresolved
upstream access restriction, not a verified missing page or application outage.
No 403 is treated as success. See [current identities and recovery instructions](CURRENT_RELEASE.md).

These dated observations are not promises of future results. Generated frames
establish software behavior, not physical-camera accuracy or device validation.

## Historical r1 operational checkpoint — preserved

The live site now serves the experimental camera profile, with the frozen
benchmark under **Evidence**. [Current release status](CURRENT_RELEASE.md)
separates this deployment from the historical observations below.

- [Camera release run 35847456472](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35847456472)
  passed predeployment and HTTPS smoke (five tests each) and exact comparison
  of all 46 published files against the approved inventory.
- [First camera monitor run 35847916308](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35847916308)
  passed all five generated-camera smoke tests. The profile variable is
  `camera-experimental-r1`; its weekly check runs Mondays at 05:37 UTC. The old
  benchmark-root smoke is inactive while this profile is selected.
- [Main-source CI 35848168116](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35848168116)
  passed after the separate import-order correction at `4f6bb44`.
- [Documentation check 35848362866](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35848362866)
  remains failed: 99 of 100 link occurrences passed; the sole failure was an
  external MDPI paper returning HTTP 403. This is not a confirmed missing
  page or application outage, and the failure was not suppressed.

These are the latest recorded runs at this documentation checkpoint, not a
claim that future runs passed. Camera checks use generated frames, never physical
hardware or visitor photos. The camera profile adds cancellation, retake,
permission and session-file states described in its
[system card](CAMERA_SYSTEM_CARD.md). Its output has no validated accuracy,
calibrated interval or reliable-abstention claim. No visitor telemetry is added.
Follow the [camera release and rollback procedure](CAMERA_RELEASE.md) for the
active profile; historical benchmark-only statements below are not its contract.

## Status addendum — 23 September 2026

The dated source-freeze and candidate-stage statements below describe their
original checkpoints. The monitoring correction was subsequently published:
[source CI at `567c5b3`](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35594696311)
passed, and the
[revised monitor](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35594724981)
completed with a passing live-page/integrity/fixed-replay job and a failing
tracked-documentation-link job. Both observations are retained; neither an
application outage nor a clean documentation-link audit follows from that
mixed result.

The later [main-source CI failure at `299c64a`](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35604443399)
followed documentation deletions and must be addressed separately. It does not
change the approved v1.0.2 tag or establish the current availability of the live
site. These links identify recorded runs, not a new live check performed by this
addendum. See the [correction record](MONITORING_CORRECTION.md) for the preserved
history and current publication clarification.

No monitoring failure is waived. This source-documentation repair does not
dispatch a workflow, redeploy the app, update a release tag, or add scientific,
visitor-data or real-world accuracy claims.

## Historical operational record — preserved

**Source-freeze snapshot (20 September 2026):** this was a Gate C-approved
benchmark/failure-explorer candidate for local Gate D review only. Public
deployment and Gate D approval had not occurred at this checkpoint.

**Operations update (21 September 2026):** v1.0.2 was subsequently approved,
deployed and live-verified. Its first weekly run passed live checks but failed
documentation links. The [monitoring correction](MONITORING_CORRECTION.md) is
a local-only successor, not yet published; it separates those statuses without
changing the deployed app or accepting blocked/broken references as successful.

## What could be monitored without tracking visitors

After an explicitly approved deployment, the release workflow must verify the
HTTPS destination, compare every hosted file byte-for-byte with the exact
audited distribution preserved for rollback, and exercise the bundled
fixed-pair harness. The scheduled GitHub Actions live job compares the 25 tracked
`web/public` files with immutable `v1.0.2` sources (reusing the frozen `v1.0.0`
model), checks the page/model checksum, request boundaries and fixed replay,
and preserves observation artifacts for 90 days. It does not byte-compare
generated JavaScript, runtime or legal build assets; the separate release check
covered all 36 deployed files. It must not add client analytics, accept visitor
images or collect predictions. The proposed separate documentation job checks
only tracked project Markdown and retains its own unresolved-reference status.

Before the original deployment, only local build/browser evidence existed.
Live-release and first-monitor observations now exist; local correction tests
do not establish successful hosted execution of the proposed successor.

## Current failure behavior

| Failure | Visitor/maintainer behavior | Verification evidence |
|---|---|---|
| Frozen summary or example record is malformed | Build/test fails; do not publish inconsistent evidence | Schema/unit tests and fixed-data tests |
| Fixed example asset is unavailable | Show an explicit accessible asset error; do not substitute or fabricate an image | Production-route browser test |
| Displayed metric or target differs from frozen evidence | Treat as a release blocker | Data binding and review against machine-readable reports |
| Unexpected network route is requested | Privacy/static-boundary test fails | Enumerated-request Playwright assertion |
| Benchmark model/metadata integrity mismatch | Unlinked harness remains unavailable; visible evidence explorer still identifies the failure | Checksum/version and worker-integration tests |
| Fixed-pair harness inference exception, cancellation, worker crash, or timeout | Terminate and disable the failed worker, reject every pending replay, ignore stale responses, and show no numeric output | Focused worker-client failure tests, integration test, and public smoke |
| Public host unavailable after a future approved release | Use the local build and recorded/static evidence pack; open an incident | Scheduled smoke result |

The current visitor route has no invalid-user-image, fresh-estimate,
uncertainty-threshold, or abstention runtime state because it accepts no custom
input and produces no per-user result.

## Superseded pre-outcome failure design

> **Historical design only.** The preregistered estimator specified invalid
> image errors, preprocessing/inference failures, finite-value checks,
> uncertainty-based abstention, and suppression of unsafe numeric results. The
> product gates failed, so those states are retained only in low-level code and
> tests; they are not part of the current explorer contract.

## Incident procedure

1. Classify the incident as fatal, major, minor, or informational.
2. Preserve the affected revision/build, UTC time, smoke or local test result,
   static/model hashes, and a reproduction that uses no visitor data.
3. For evidence-integrity, attribution, privacy, or critical security issues,
   do not deploy—or disable/roll back an approved deployment—rather than place
   a warning over an invalid explorer.
4. Fix on a reviewed branch, run the full release suite, and update the change
   log, evidence inventory, and affected notices/cards.
5. If a tagged release later exists, restore the exact prior approved static
   artifact retained by the release workflow and repeat the byte-for-byte live
   comparison plus public smoke before closing the incident.

## Model-monitoring boundary

There is no production prediction service, visitor prediction telemetry, or
live ground truth. PlateGauge cannot claim real-world drift detection. In the
current candidate, “model monitoring” means only checksum/version verification
and a fixed bundled replay in the unlinked harness. Any future field-monitoring
or custom-input design requires new evidence, privacy/consent review, and
approval.

## Review period and successor publication

`PLATEGAUGE_PUBLIC_URL` is configured to the explicitly approved HTTPS Pages URL.
The fail-closed static smoke check is scheduled weekly
through the application cycle and once before each shared demo. A missing or
non-HTTPS URL is a failed workflow, not a skipped success. Stop scheduled runs
when they cease to provide value. The current published monitor is active, with
its first failed documentation result preserved. Publishing this correction and
dispatching its revised workflow require separate approval. No app redeployment
is necessary, and the v1.0.2 tag must remain immutable.
