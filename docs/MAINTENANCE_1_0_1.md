# PlateGauge 1.0.1 maintenance candidate

> Historical candidate record. D-R2 later passed CI and was approved/published
> as v1.0.1, but its release workflow failed before deployment. See the
> [v1.0.2 correction record](MAINTENANCE_1_0_2.md). The original chronology below
> is retained, not rewritten as a successful deployment.

At this snapshot, this was a D-R2 engineering candidate pending exact-source release approval.
Its isolated verification branch/PR may run hosted CI, but does not authorize
moving public main, tagging or deploying. D-R1 source
`eee743c86039707570827fea6aaa1c2e17f5287d` is public and its hosted CI failed;
it was not released or deployed. This corrective candidate builds on it.
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
  exact geometry, alpha in 254–255, at most one 8-bit RGB level of error, and exact
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
- Canonicalize archive input paths before sorting, so Windows short/full path
  aliases use the same root-relative names. Reject duplicate resolved names,
  non-regular/outside sources and linked inputs, including linked directories.
  Validate before replacing any existing output. Keep bytes and ZIP metadata
  unchanged for valid inputs; test alias output against canonical output.
- Run each synthetic preprocessing fixture independently. Record alpha ranges
  and non-opaque pixel counts as diagnostics. Do not let a failed landscape
  fixture prevent the portrait observation.

## D-R2 compatibility correction and its evidence

[D-R1 hosted run 35569365268](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35569365268)
passed Linux Python (212 tests, one dependency-path skip, 85.51% coverage), web
quality, scans and Linux portability. Windows packaging failed when the base
path resolved to `runneradmin` but the sort input retained the `RUNNER~1` alias.
The D-R2 path correction addresses the helper rather than relocating the test.

Linux WebKit's landscape fixture failed the prior exact-alpha requirement on
three attempts. Each saved buffer had 112 of 50,176 pixels at alpha 254 and the
rest at 255. RGB stayed within one level, geometry was exact, and tensor bytes
exactly matched float32 normalization of observed RGB. Production tensor
conversion ignores alpha. The previous test never reached portrait on WebKit.

The separately reviewed D-R2 test contract permits alpha 254–255 only for the
two uniform WebKit resize fixtures. RGB and tensor constraints do not change.
Alpha below 254, two-level RGB drift and wrong tensors must still fail. This
does not alter runtime pixels, model inputs, golden files, weights or frozen
predictions; it is not an arbitrary-image or cross-browser model-parity claim.
The upstream browser cause is not established by these observations alone.

## Preserved evidence and behavior

Datasets, folds, model weights, predictions, scientific metrics, all files under
`web/public`, the golden fixture files, and the claim-evidence map are unchanged.
The explorer continues to expose only fixed examples and suppress fresh numeric
output. The paired model's negative result and all prior limitations stand.
This work does not establish applicant-performed independent reproduction.

## Historical D-R1 local verification limits

Local verification uses Windows and separately materialized Windows/LF Git
checkouts. LF checkout verification is not a native Linux run. In particular,
the original Linux WebKit failure supplied hashes but no pixel buffers; its
error magnitude cannot be inferred from those hashes. The one-level limit is
a fixed compatibility requirement, not a claim that the prior failure met it.
Hosted Linux must pass this limit without widening it before deployment.

The initial local D-R1 amendment excluded training. Existing synthetic Ridge-fitting
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
Subsequent separately approved synthetic unit fitting closed the coverage gap,
but the hosted D-R1 failures above blocked release. Their evidence is retained.
No research or neural training occurred. D-R2 validation may run those same
seven synthetic fitting tests, without saved research models or research claims.

## Current release condition

The new exact candidate must pass native Linux/Windows CI and unchanged quality,
security, licensing and evidence-integrity checks. The CI run tied to the exact
candidate is authoritative; historical local counts above are not its results.
No remaining failure may be waived. Publication approval, approval-only child,
release tag, deployment and live verification remain separate future actions.
