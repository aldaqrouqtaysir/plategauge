# Security review

> **Status: local Gate D candidate reviewed on 20 September 2026.** The
> technical candidate checks described below pass locally. Gate D approval,
> source commit and tag, protected Pages configuration, deployment, and live
> public smoke testing remain pending. This document does not authorize release.

## Current public surface

The Gate C outcome is a static benchmark and failure explorer, not an upload
estimator. The browser interface exposes ten fixed, disclosed benchmark pairs
drawn from frozen outer-fold predictions. The normal visitor route does not
initialize the model. A deliberately unlinked `?benchmark=1` verification
route loads the bundled FP32 ONNX model in a Web Worker and can replay the
selected fixed pair, but it does not show a new numeric estimate. There is no file input, camera access,
user-supplied mass, account, database, application API, analytics, cookie, or
client-side history.

This boundary removes the original design's untrusted-image parser and
decompression-bomb attack surface. The relevant remaining assets are static
HTML/CSS/JavaScript, twenty attributed JPEGs, an ONNX model, same-origin WASM,
and bundled legal documents.

## Threats, controls, and local evidence

| Threat | Current control | Local verification | Status |
|---|---|---|---|
| Accidental restoration of an unrestricted estimator | No file input or camera path; fixed-pair allowlist; numeric output suppressed; benchmark-only copy | Production Playwright smoke checks zero file inputs, ten fixed pairs, and absence of numeric runtime output | Pass |
| Image or prediction exfiltration | No user images or upload/API path; no analytics or third-party scripts; requests restricted to allowlisted same-origin `GET` assets | Full-navigation production smoke captures every request from first navigation; static audit finds no remote runtime resource | Pass locally |
| Unexpected files or raw data in the deployed bundle | Exact fail-closed allowlist; raw archives, workbooks, source maps, tabular source data, and unknown images rejected | `reports/release/static-bundle-audit.json`; negative tests inject a forbidden file | Pass |
| Model or manifest substitution during packaging | Canonical, staged, and built ONNX bytes must match SHA-256 `9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675`; manifest copy must be byte-identical | Static bundle audit plus model-tampering negative test | Pass locally |
| Example-image substitution or missing attribution | All twenty JPEG hashes must match the frozen example manifest; NOTICE and privacy/AI-assistance documents are copied into the build and hash-checked | Static bundle audit verifies image hashes and exact legal-file copies | Pass |
| Cross-site scripting or remote-code loading | No user-controlled display metadata; React text rendering; restrictive resource CSP; no `dangerouslySetInnerHTML`, remote import, CDN, objects, or third-party runtime assets | Source/static scan and built-site resource inventory | Pass locally |
| Clickjacking/framing | Read-only interface has no account, form, upload, or consequential action. A meta-delivered CSP cannot enforce `frame-ancestors`, and the current deployment design has no verified anti-framing response header | Documented residual risk; do not claim anti-framing protection without a verified HTTP response header | Accepted low-consequence residual |
| Dependency compromise or incompatible license | Python and JavaScript lockfiles; network-refreshed vulnerability audits; generated Python and production-JavaScript license inventories; release CI repeats scans | `reports/security/dependency-scan-observations.json` records zero known advisories at the scan time | Pass at observation time |
| Secret or build-host path disclosure | No runtime secret is required; candidate-tree and built-site scans check high-confidence secrets and absolute host paths; raw data remains ignored | Candidate-tree scanner in `src/plategauge/gate_d_audit.py` and the static bundle audit | Pass locally; history scan awaits first commit |
| Main-thread denial of service or hung replay | Inputs are fixed, size-bounded bundled examples; inference executes in a Web Worker; each replay has cancellation and a bounded timeout; worker failure terminates and disables the client rather than leaving pending work | Unit failure-path tests and production smoke complete real fixed-pair inference with the release model | Pass for the fixed harness |
| Misleading model claims | Gate C failure boundaries are visible; new-image input and numeric estimates are disabled; result is described as a benchmark/failure explorer | UI assertions and claim review | Pass |
| Missing legal/privacy disclosure | Built footer links to NOTICE, privacy notice, dependency inventory, and AI-assistance record; it states the GitHub hosting-metadata limitation | Legal-file identity checks and production browser smoke | Pass locally |

## Browser and network policy

The built page uses a restrictive meta-delivered Content Security Policy for
supported resource directives: application code, styles, workers, images,
model, WASM, and legal files are same-origin (with `data:` allowed only where
required by the static UI); `connect-src` is limited to self; object/embed
execution is disabled. [CSP Level 3](https://www.w3.org/TR/CSP/) requires
`frame-ancestors` to be ignored in a meta element, so this project does **not**
claim framing protection without a verified HTTP response header. The production test
starts request capture before navigation and rejects a request that is not an
allowlisted same-origin `GET`.

This supports a bounded statement: PlateGauge has no application-level image
upload or analytics path. It is not a promise that visiting a hosted page is
anonymous. GitHub Pages, the browser, DNS, and network intermediaries may
process ordinary request metadata as described in `docs/PRIVACY_NOTICE.md`.

## Supply-chain and integrity boundary

The model checkpoint revision, pretrained-weight digest, exported model digest,
dataset attribution, runtime dependency inventory, and release manifest are
recorded. Third-party workflow actions are pinned to full commit identifiers;
Python, Node, pnpm, and the environment installer are version-pinned. The
release workflow is designed to check out the exact `v1.0.0` tag,
accept only the separately reviewed approval child commit, rebuild the site,
rerun audits, inspect the exact distribution, and run real-model production
smoke tests before Pages deployment. It preserves that audited distribution for
90 days, then verifies every live file byte-for-byte and repeats the real-model
request-boundary smoke after deployment.

Audit results are time-sensitive and do not prove that a dependency is safe.
Any new high/critical exploitable advisory in a shipped path, model/hash
mismatch, unexpected network request, unexpected bundle file, or failed
production smoke blocks release pending review.

## Findings and residual limitations

No fatal or major technical finding is open in the current local candidate.
The following release-state items remain deliberately unresolved:

- There is no source commit or history yet, so a history-wide secret scan and a
  commit-bound artifact manifest cannot exist.
- At the 20 September 2026 local review there was no release tag, remote,
  protected GitHub Pages environment, or public URL, so the live smoke test
  failed closed and had not run. Any later status must be verified from its
  tag, approval record, deployment evidence, and public-smoke report.
- Same-origin delivery still trusts the selected hosting platform and browser.
  The application does not perform an independent in-browser cryptographic
  verification of every fetched asset; build and release gates bind the bytes.
- Vulnerability inventories describe the observation time only and must be
  refreshed by release CI.
- Anti-framing protection is not available from the current GitHub Pages/static
  meta-CSP configuration. This is accepted only because v1 is read-only and has
  no visitor-controlled or consequential action; a future interactive version
  must use a host that can send a verified `Content-Security-Policy` response
  header.
- The model's scientific limitations remain the primary user-safety issue. The
  interface must stay a fixed benchmark/failure explorer unless a separately
  evaluated later version earns a broader claim.

These are pending authorization/infrastructure checks or explicit limitations,
not evidence that a public release has occurred.
