# Security policy

## Supported versions

As of 23 September 2026, the
[camera-experimental-r5 prerelease](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/camera-experimental-r5)
is the deployed, live-verified camera profile.
[v1.0.2](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/v1.0.2)
remains the latest stable benchmark release and rollback target. Report the
affected release, route and source revision when possible. See
[current release status](docs/CURRENT_RELEASE.md).

Neither profile is a production food-weight estimator or a service with a
support-level guarantee. Camera-photo accuracy has not been validated.

Any correction is reviewed as a new source change; existing release tags and
frozen evidence are not rewritten. Publishing source does not by itself
authorize deployment. The release approval and verification requirements in
[the current operating guide](docs/CURRENT_RELEASE.md#operating-the-current-release) still apply.

## Reporting a vulnerability

Do not publish a working exploit or include sensitive images in a public issue.
Use **Security > Advisories > Report a vulnerability** on GitHub. Private
reporting was enabled for this repository on 23 September 2026. If unavailable,
open a minimal issue asking for a private contact channel without disclosing
exploit details. Dependency vulnerability alerts are also enabled; an empty
alert list is not a guarantee that all dependencies are safe.

Include the affected version, browser/operating system, reproduction steps,
impact, and whether any image bytes left the browser. Receipt should be
acknowledged within seven days. This is a small research project and cannot
promise a production-service response time.

## Current camera security boundaries

- Camera access starts only after an explicit action and browser permission;
  no microphone is requested. Inference is another explicit action. Opening a
  route does not activate hardware or start estimation.
- Photos, optional starting mass and estimates are processed locally. No
  inference API, account, analytics, application database or automatic photo
  history exists. GitHub Pages and the network still handle ordinary requests
  for static assets; this is not a zero-network claim.
- Explicit Save session downloads an **unencrypted** file containing photos,
  model crops and any entered mass. The browser/OS controls downloaded files
  and backups; Clear cannot delete those copies. Resume only files you trust.
  Checksums detect corruption, not malicious edits or forged capture provenance.
- Camera streams stop on hide, navigation and cleanup. Hiding clears estimates
  but retains the in-memory pair; Clear or reload releases it. Forensic erasure
  of browser/OS memory is not promised.
- The model is hash-checked before use in a dedicated worker. Input/work bounds,
  cancellation and worker termination constrain processing. CSP and same-origin
  assets reduce exposure but do not eliminate browser or dependency risks.
- The camera profile requires a secure, top-level page on the configured host
  or loopback. This runtime check is not a verified HTTP anti-framing header.
- Non-food scenes, mismatched foods and incorrect user-entered mass can produce
  misleading outputs. The app does not certify inputs or model accuracy; do
  not use outputs for medical, nutritional, purchasing or safety decisions.

See the released [camera privacy notice](docs/CAMERA_PRIVACY_NOTICE.md) and
[camera system card](docs/CAMERA_SYSTEM_CARD.md). Their candidate-stage status
wording describes the frozen source checkpoint; publication status is recorded
separately in [current release status](docs/CURRENT_RELEASE.md).

## Historical v1.0.2 benchmark boundaries

- The Gate C-approved benchmark visitor interface is a fixed benchmark and failure
  explorer. It accepts no visitor files, camera input, mass input, or free-form
  metadata and renders no new numeric estimate.
- The normal visitor route does not initialize the model. A deliberately
  unlinked `?benchmark=1` verification route can replay only bundled,
  hash-bound example pairs in a Web Worker through ONNX Runtime Web/WASM; its
  result remains non-numeric.
- Historical validators for an earlier upload-estimator design remain covered
  by tests, but they are not part of the public v1 interface or its security
  claim.
- No user account, server API, database, persistent image store, analytics, or
  third-party script is part of v1.
- A static site cannot prevent GitHub Pages or the user's network from handling
  ordinary request metadata. The project claims only that PlateGauge does not
  accept or upload visitor image content.
- Model integrity is checked with a published SHA-256 digest.
- The in-document CSP restricts supported resource types, but the current
  GitHub Pages deployment design has no verified anti-framing HTTP response
  header. Framing/clickjacking therefore remains an explicit, low-consequence
  residual risk for this read-only interface.

The historical `docs/SECURITY_REVIEW.md` and `docs/PRIVACY_NOTICE.md` describe
that benchmark profile, not the later camera extension. Current operational
observations appear in [monitoring](docs/MONITORING_AND_FAILURES.md).
