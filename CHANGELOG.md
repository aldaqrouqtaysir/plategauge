# Change history

This file distinguishes repository maintenance from deployed releases. Existing
tags, scientific evidence and historical failed checks remain unchanged.

## 23 September 2026 - postrelease maintenance

- Align the README, reviewer walkthrough, development entry points and security
  policy with the published experimental camera profile.
- Add a current release overview and dated monitoring summary, preserving
  frozen cards, historical media, results and unsuccessful observations.
- Add actual, camera-off screenshots of the published interface, with provenance.
- Run all three engines of the camera regression suite on future source changes
  in CI, including three new empty-page device-report download scenarios. The
  new job never deploys and uploads only allowlisted result metadata.
- Enable private security reporting and dependency vulnerability alerts; update
  repository metadata to describe the experimental camera and benchmark.
- Documentation updates do not deploy a new site or claim new model accuracy.
- The first maintenance CI run rejected the two new interface screenshots under
  the raw-data publication safeguard. Preserve that failure; accept only the
  two reviewed paths with their exact SHA-256 hashes and regression-test that
  unapproved or altered image files still fail. No scientific hash was repaired.
- Pin ordinary CI and weekly-monitor Linux runners to Ubuntu 24.04, avoiding
  the announced `ubuntu-latest` transition beginning 19 October. Frozen release
  workflows and existing release tags are unchanged.
- Retain the runner-pin follow-up failure: the monitoring contract test still
  expected the old floating Linux alias. Update that assertion to require the
  pinned Linux runner while preserving its Windows/runtime safety assertions
  and the deliberately historical failing-setup fixture.

## 23 September 2026 — import-only CI correction

Commit `4f6bb44f27bb7185393cdc856bbd6fb0e8ca6f5b` corrected import ordering in
the synthetic Pillow fixture generator. The subsequent
[CI run 35848168116](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35848168116)
passed. The original failed run is retained. No deployed file, model, tag or
scientific value changed.

## 23 September 2026 — camera-experimental-r1

Published the separately approved experimental camera workflow: real capture,
crop review, explicit local inference, session save/resume and device-check
export. The existing paired baseline and frozen benchmark remained unchanged.

The [release workflow](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35847456472)
passed deployment and live verification; the
[first camera monitor](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35847916308)
also passed. These generated-input tests are software evidence, not a physical
camera test or real-photo accuracy validation. The separate documentation
monitor's external HTTP 403 remained unresolved.

See [the release overview](docs/CURRENT_RELEASE.md) for identities and checks.

## Historical benchmark releases

The stable [v1.0.2 release](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/v1.0.2)
is a fixed-example benchmark/failure explorer and the camera rollback target.
Its model, predictions and scientific conclusions are preserved. Earlier
maintenance is recorded in [v1.0.1 notes](docs/MAINTENANCE_1_0_1.md),
[v1.0.2 notes](docs/MAINTENANCE_1_0_2.md) and
[the monitoring correction](docs/MONITORING_CORRECTION.md). Those dated records
retain the original failures and must not be read as the current camera contract.
