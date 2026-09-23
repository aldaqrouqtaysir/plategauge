# Camera r2: footer presentation maintenance

`camera-experimental-r2` is a footer-only application update to the experimental
camera release. It removes the two-paragraph text block from the Evidence
footer and closes the unused layout column. Privacy, notices, dependency
licenses, source and contribution-document links remain available. The linked
records, camera behavior, model, data and scientific conclusions are unchanged.

## Source and delivery

- Application source: `5d67e29bf79d088e7c4a6903c6ce2c5c58a10f1a`.
- [Exact 46-file inventory](../release/camera-r2/inventory.json), SHA-256
  `d885da02a49fdc54863656ff3c368b41aa8c932c2446bd3bfca6826e9de3009b`.
- Exact archive `camera-experimental-r2.zip`, SHA-256
  `492e828d7e57e2decd2e9c1e2fcdd46e0e4f15ad01f94618d5e6d9394938f77d`.
- [Local verification record](../release/camera-r2/verification-evidence.json).
- [Published release](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/camera-experimental-r2)
  and [delivery workflow](https://github.com/aldaqrouqtaysir/plategauge/actions/workflows/release-camera-r2-pages.yml).

Publication follows the same exact-artifact discipline as r1: a new operations
commit, a fresh approval-only child, an immutable tag, archive verification,
generated-input local smoke, deployment, then complete live-byte verification
and HTTPS smoke. Source builds are not silently substituted for this archive.
Main-branch maintenance does not deploy automatically. The release-specific
workflow can run only at the exact r2 tag; all prior tags and r1 records remain
unchanged. A failed check must remain visible and must not be resolved by
accepting whatever the server happens to return.

## Authorization and claim boundaries

The user requested removal of the pictured footer block after authorizing
routine maintenance, publication and completion without repeated approval
prompts. The new approval record documents that bounded request and delegated
authority; it is not a claim that the applicant independently reviewed every
source line, reproduced the model or completed a physical-device test.

No new accuracy, impact, authorship, calibration, production-readiness or
application-use claim is made. Existing contribution/privacy records remain
byte-identical. Experimental camera accuracy remains unvalidated.

## Monitoring and recovery

Set `PLATEGAUGE_ACTIVE_PROFILE=camera-experimental-r2` only after successful
deployment and live checks. The dedicated weekly r2 workflow then verifies
the exact tag, inventory and generated-camera journey. R1 monitoring remains
available but inactive; the old benchmark root smoke explicitly skips both
camera profiles. Documentation link monitoring remains independent.

The r2 rollback workflow restores the same byte-verified v1.0.2 benchmark
archive retained by r1. The immutable r1 camera release workflow can also
restore the previous camera release; verify its complete inventory and HTTPS
journey before selecting the r1 monitoring profile. Never move a historical
tag or replace a release asset to perform rollback. See the
[r1 delivery and rollback record](CAMERA_RELEASE.md).

Automated checks use generated frames, never the user's physical camera or
photos. Reports do not establish real-device compatibility or new-photo accuracy.
