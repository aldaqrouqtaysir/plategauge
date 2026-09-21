# Monitoring, incidents, and failure handling

**Source-freeze snapshot (20 September 2026):** this was a Gate C-approved
benchmark/failure-explorer candidate for local Gate D review only. Public
deployment and Gate D approval had not occurred at this checkpoint.

## What could be monitored without tracking visitors

After an explicitly approved deployment, the release workflow must verify the
HTTPS destination, compare every hosted file byte-for-byte with the exact
audited distribution preserved for rollback, and exercise the bundled
fixed-pair harness. A scheduled GitHub Actions smoke check then compares every
frozen public evidence, example, model/runtime, and legal asset with the
`v1.0.1` sources (reusing the frozen `v1.0.0` model); checks version, model checksum, internal links, request
boundaries, and fixed-pair execution; and preserves the observation artifacts
for 90 days. It must not add client analytics, accept visitor images, or collect
predictions.

No live public smoke monitoring is active before deployment. Current evidence
comes from local production-build and browser tests.

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

## Review period after a future release

If Gate D later authorizes deployment, configure `PLATEGAUGE_PUBLIC_URL` to the
explicit HTTPS Pages URL and run the fail-closed static smoke check weekly
through the application cycle and once before each shared demo. A missing or
non-HTTPS URL is a failed workflow, not a skipped success. Stop scheduled runs
when they cease to provide value. This is a proposed release operation, not a
currently active monitor.
