# Camera presentation maintenance: r6

R6 makes the capture page less text-heavy. It removes the detached hero
sentence, shortens the capture checklist and session guidance, and places the
long privacy/storage explanation in a keyboard-accessible disclosure.
Experimental-estimate and unencrypted-file warnings remain visible beside
the relevant actions. All capture, session and inference actions are unchanged.

## Frozen artifact

| Binding | Value |
| --- | --- |
| Release tag | `camera-experimental-r6` |
| Application source | `d2fc03257e8ebfdae3923aa454fa8b3645212731` |
| Camera inventory | 45 files |
| Inventory SHA-256 | `a95a1770aaae2373887fd3bc38d8adcd8f9f856c6b02c41bd92ebec3f68c2fc8` |
| Camera ZIP SHA-256 | `b4d8dba94790881b434796769f9735932f2ae0cf0e7e7acf12638530a6098c96` |

The release workflow delivers the exact verified archive, not a rebuild.
An approval-only child binds source, operations, evidence and rollback under
the user's delegated maintenance authority. It does not assert independent
applicant reproduction. Changes to `main` do not deploy automatically.

## Verification and limits

The [verification record](../release/camera-r6/verification-evidence.json)
distinguishes local checks from subsequent hosted outcomes. The
[eight-check archive harness](../release/camera-r6/README-smoke.md) retains
privacy, camera lifecycle, session, pinned-model and exact-asset checks, and
now checks the concise introduction and collapsed privacy details. Browser
regressions cover four widths and keyboard expansion without automatic camera
or inference. Only generated images are used in tests.

No model, dataset, folds, predictions, scientific metrics or calibration
changes. Camera-photo accuracy and operational usefulness remain unvalidated.
Historical tags and release evidence remain immutable, including undeployed
r4. Rollback still restores the bound 36-file `v1.0.2` benchmark archive.
See [Current release](CURRENT_RELEASE.md) for actual publication, deployment
and monitoring outcomes; this artifact record alone does not establish them.
