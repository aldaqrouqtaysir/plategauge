# Camera reliability maintenance: r4

This successor addresses the [comprehensive maintenance audit](MAINTENANCE_AUDIT_2026-09-23.md).
It preserves unsaved photos when opening links in another tab, fixes keyboard
skip-link visibility, aligns mass/session validation and provides safe recovery
guidance for known estimation errors. Repository maintenance also improves
dependency handling, media preservation, CI and prospective numerical utilities.

## Frozen artifact

| Binding | Value |
| --- | --- |
| Release tag | `camera-experimental-r4` |
| Application source | `1f55a7b21cf0aff395df4930d0232a0b0838361d` |
| Camera inventory | 45 files |
| Inventory SHA-256 | `42f7b26fe0b7349cec30537cf84bddc14db9cc4b90d4a26ca1ab213b2174eecb` |
| Camera ZIP SHA-256 | `bab8d848d2ba476a1bb9b12595327896ffa21893de1525e95c3e9cc85e2f6d41` |

The release workflow serves the exact verified ZIP, never a rebuild. An
approval-only child binds source, operations, archive, evidence and rollback.
A change to `main` does not deploy automatically. Publication uses the user's
delegated maintenance authority, not a claim that the applicant independently
performed the recorded checks.

## Checks and unchanged boundaries

The [eight-check exact-artifact harness](../release/camera-r4/README-smoke.md)
checks keyboard visibility, new-tab capture retention, actual-exit cleanup,
generated before/after inference with the existing hash-pinned model, explicit
session files, route boundaries and exact static asset responses. Synthetic
camera installation is independently checked before any capture action. The
test never calls a physical camera or uses personal photos.

The [verification record](../release/camera-r4/verification-evidence.json)
separates local outcomes from hosted CI and publication. Check
[Current release](CURRENT_RELEASE.md) for observed deployment status.

No model, dataset, fold, frozen prediction, scientific value or accuracy claim
changes. The [utility erratum](RESEARCH_UTILITY_ERRATA.md) preserves legacy
calibration by default; its corrected prospective rank is not used by the
website. No public confidence interval is introduced.

All previous tags and artifacts remain immutable. The bound rollback still
restores the exact 36-file `v1.0.2` benchmark archive, not an older camera app.
Monitoring must match the artifact actually served; a failed camera check must
not be hidden by changing its profile. Real-camera accuracy and operational
benefit remain unvalidated.
