# Camera reliability maintenance: r5

This release carries the fixes in the [comprehensive maintenance audit](MAINTENANCE_AUDIT_2026-09-23.md): capture retention across new-tab navigation, visible keyboard skip links, consistent mass/session validation, actionable safe errors, and repository maintenance safeguards.

## Why r5 follows an undeployed r4

[R4 release verification](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35898553111) passed seven checks but timed out waiting for a raw Privacy Markdown link to open a new page on Linux. Deployment and live verification were skipped. Its tag, archive and failed evidence remain immutable. R5 tests modified navigation through the existing HTML Evidence link instead, retaining actual popup interaction, original-photo retention, strict network checks and cleanup on normal departure. The underlying platform cause is not conclusively established; no MIME behavior or product code was changed to mask it.

## Frozen artifact

| Binding | Value |
| --- | --- |
| Release tag | `camera-experimental-r5` |
| Application source | `40493849af148124a45b6a6c65d9c9146c03fdb4` |
| Camera inventory | 45 files |
| Inventory SHA-256 | `4f187ffba720de77cc2349d1fcdbd2b29d03c131aac132006b036fc8514e57e5` |
| Camera ZIP SHA-256 | `cd0b6e80624422dacfb052fff4b9f393668f769b384dd68772be41f4aa0cbef2` |

The exact verified ZIP is deployed, never rebuilt. An approval-only child binds source, operations, archive, evidence and rollback. Publication uses delegated maintenance authority; it does not claim independent applicant reproduction or review of this exact commit. Updating `main` alone cannot deploy.

## Checks and limits

The [eight-check artifact harness](../release/camera-r5/README-smoke.md) checks generated captures with the unchanged pinned model, explicit local session files, keyboard access, navigation lifecycle, inert routes and exact static responses. It never uses physical cameras or personal images. The [verification record](../release/camera-r5/verification-evidence.json) separates local results from subsequent hosted outcomes. See [Current release](CURRENT_RELEASE.md) for observed deployment status.

Application and numerical code are unchanged from audited source `1f55a7b21cf0aff395df4930d0232a0b0838361d`; A5 adds only future workflow-maintenance exclusions beyond intervening release operations. No model, dataset, fold, prediction, scientific metric or claim changes. The [prospective utility correction](RESEARCH_UTILITY_ERRATA.md) is not enabled in frozen orchestration or the website.

All preceding tags remain immutable. Rollback restores the bound 36-file `v1.0.2` benchmark archive. Monitoring must match the artifact actually served. Real-camera accuracy, field usefulness and operational benefit remain unvalidated.
