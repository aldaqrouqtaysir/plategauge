# Security policy

## Supported versions

As of 23 September 2026, the latest published benchmark release is
[v1.0.2](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/v1.0.2).
Report security issues against that release or the current development branch.
This is a research benchmark and failure explorer, not a production food-weight
estimator or a service with a support-level guarantee.

Any correction is reviewed as a new source change; existing release tags and
frozen evidence are not rewritten. Publishing source does not by itself
authorize deployment. The release approval and verification requirements in
[the deployment guide](docs/DEPLOYMENT.md) still apply.

## Reporting a vulnerability

Do not publish a working exploit or include sensitive images in a public issue.
Use GitHub's private vulnerability-reporting feature for the repository when
available. If it is not enabled, open a minimal issue asking the maintainer for
a private contact channel without disclosing exploit details.

Include the affected version, browser/operating system, reproduction steps,
impact, and whether any image bytes left the browser. Receipt should be
acknowledged within seven days. This is a small research project and cannot
promise a production-service response time.

## Security boundaries

- The Gate C-approved visitor interface is a fixed benchmark and failure
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

See `docs/SECURITY_REVIEW.md`, `docs/PRIVACY_NOTICE.md`, and
`docs/MONITORING_AND_FAILURES.md` for the release checklist and limitations.
