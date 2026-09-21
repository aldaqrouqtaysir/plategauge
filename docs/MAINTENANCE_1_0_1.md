# PlateGauge 1.0.1 maintenance candidate

This is a local engineering candidate pending separate publication approval.
It descends from public source `9367457b8c793b5abd3a97ba33dc41cb4bf4e3ff`.
The public `v1.0.0` tag remains immutable. This candidate contains no new Gate D
approval artifact and cannot pass the publication gate without one.

## Corrections

- Reconstruct the historical fold-amendment audit fixture explicitly with
  CRLF bytes on every host. Its original pinned digest and scientific contents
  stay unchanged. Pin the claim-map checkout to its existing LF byte contract.
- Verify regenerated synthetic PNGs by exact decoded pixels, geometry, and
  tensor hashes. Continue verifying the committed files' original byte hashes;
  only lossless encoder output is allowed to differ across platforms.
- Retain exact preprocessing hashes for Chromium, Firefox, and WebKit's
  patterned identity fixture. For WebKit's two uniform resize fixtures, require
  exact geometry, opaque alpha, at most one 8-bit RGB level of error, and exact
  CHW float32 normalization of the observed pixels. Tests reject larger drift,
  channel swaps, malformed buffers, and invalid or incorrect tensor values.
- Use Python 3.12.10 solely to bootstrap uv on Windows, where setup-python does
  not distribute 3.12.14. uv then installs its pinned managed Python 3.12.14 for
  the actual environment and checks. Linux and Windows tests still execute on
  3.12.14, using the existing dependency lock.
- Replace the first-push commit-range action with checksum-pinned Gitleaks
  8.24.3 scanning `--all` fetched history, including root commits. Reject shallow
  history. Preserve redacted scan reports and browser diagnostics after failures.
- Build the static distribution before the Python release tests that audit it.
  A fresh tagged checkout cannot satisfy those tests before `web/dist` exists.
- Identify software/packages/citation as 1.0.1 while keeping the frozen model
  manifest at v1.0.0. The release verifier allows only that explicit pairing,
  still binding all four evidence hashes and the new approved source commit.

## Preserved evidence and behavior

Datasets, folds, model weights, predictions, scientific metrics, all files under
`web/public`, the golden fixture files, and the claim-evidence map are unchanged.
The explorer continues to expose only fixed examples and suppress fresh numeric
output. The paired model's negative result and all prior limitations stand.
This work does not establish applicant-performed independent reproduction.

## Verification limits

Local verification uses Windows and separately materialized Windows/LF Git
checkouts. LF checkout verification is not a native Linux run. In particular,
the original Linux WebKit failure supplied hashes but no pixel buffers; its
error magnitude cannot be inferred from those hashes. The one-level limit is
a fixed compatibility requirement, not a claim that the prior failure met it.
Hosted Linux must pass this limit without widening it before deployment.

The current amendment excludes training. Existing synthetic Ridge-fitting
unit tests remain in the repository but are excluded from local D-R1 execution;
a private verification guard fails on any unexpected fitting/backpropagation.
No scientific evaluation is rerun. New temporary unit-test data and frozen
fixed-example inference are used only for engineering verification.

All 205 executed Python tests passed (one dependency-path skip, seven fitting
tests deselected). The restricted run measured 84.07% branch-aware coverage,
so the unchanged 85% full-suite gate remains unverified and failed for that
restricted invocation. It is not reported as a fully passing Python CI run.
All 88 web unit tests and 27 browser cases passed locally, followed by two
ONNX integration cases and two production-bundle/privacy cases. A fresh,
isolated copy of the pinned Firefox browser was needed because the previously
cached installation lacked its `mozglue` assembly.

The original hosted failure remains visible in
[CI run 35564362431](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35564362431).
Local test records accompany the exact candidate commit in its review package.
Hosted checks, time-sensitive audits, publication, tag creation, deployment,
and live verification remain separate future actions.
