# Camera presentation maintenance: r3

This release cleans up the current presentation and improves metric spacing,
captions and responsive layout. The experimental camera workflow and frozen
benchmark remain separate; no model, prediction, scientific value or validation
claim changes.

## Frozen artifact

| Binding | Value |
| --- | --- |
| Release tag | `camera-experimental-r3` |
| Application source | `62efadcfd342a193458036912b38b0a613bf94be` |
| Camera inventory | 45 files |
| Inventory SHA-256 | `ddf3fd89a19aa2032bec60ab16a9a52decfc59be782dc73df04d093dd6f524f3` |
| Camera ZIP SHA-256 | `4708f46dc5502b73e50f4750603b063c50740d5846ec72a40a0872c0e3a954c4` |

The independent release verifier binds the inventory, archive, verification
evidence and approval-only child to this source. The publication workflow serves
that archive, not a rebuild. A commit on `main` does not deploy the site.

## Verification and boundaries

The [release smoke harness](../release/camera-r3/README-smoke.md) checks inert
startup, generated camera input with the unchanged pinned model, explicit local
session restore, evidence navigation, responsive metric spacing and retirement
of the obsolete static resource. Its negative resource check requires a 404
without following redirects or collecting a response body. These checks do not
establish real-camera accuracy or field validity.

Exact observations belong in the
[verification evidence](../release/camera-r3/verification-evidence.json);
the presence of this document is not a successful deployment claim. Consult the
[current release overview](CURRENT_RELEASE.md) for public status.

Historical releases remain unchanged. Recovery uses the separately bound,
unchanged 36-file `v1.0.2` benchmark archive and its original resources; it is not
an experimental-camera release. The dedicated rollback workflow verifies every
restored file. Monitoring must match the artifact actually served, with failed
camera evidence retained.
