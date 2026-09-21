# Deployment guide

> **Source-freeze status (20 September 2026):** the exact local static candidate
> and guarded release workflow were implemented and passed the local technical
> audit. No source commit, Gate D approval, tag, remote, deployment,
> or live URL existed. Do not publish a demo URL until the approval-bound
> workflow and live checks pass.

## Target architecture

GitHub Pages may serve a static, versioned React benchmark/failure explorer,
ONNX model, release metadata, and ONNX Runtime Web/WASM assets from one origin.
The public route accepts only fixed disclosed examples and suppresses fresh
numeric output. The fixed-pair integrity/performance replay uses single-threaded
WASM in a Web Worker. There is no API, database, authentication, telemetry,
secret, or arbitrary-image input.

## Release prerequisites

- Gate C selected the benchmark/failure explorer on 20 September 2026 with the
  Gate C review memo's claim boundaries.
- Production web build and all Python/web/Playwright/accessibility/privacy checks
  pass from lockfiles.
- Model, frozen result, example, and release metadata have SHA-256 digests.
- PyTorch–ONNX maximum prediction drift is ≤`1e-4`.
- License inventory and attribution are complete.
- Public example assets have redistribution permission.
- README, system/model cards, privacy notice, and claim map agree.
- The Gate C review covered five successes, five failures, and all public wording.

## Approval-bound release flow

1. Complete contribution-language review. Either record applicant-performed
   independent frozen-path reproduction before making that claim, or retain the
   explicit public statement that independent reproduction is not established.
2. Sanitize the prospective public tree, rerun the local audit, create the
   immutable source commit, and let the named maintainer inspect its exact identity.
3. Obtain explicit Gate D approval for that source commit and public claim set.
4. Create only the separately verified approval-record child commit, then tag
   that approved child `v1.0.1`; no other source change may enter the tag.
5. Configure the repository and required-reviewer Pages environment.
6. Let `.github/workflows/release-pages.yml` check out exactly
   `refs/tags/v1.0.1`, verify the parent/approval relation, install from locks,
   refresh vulnerability/license/history scans, rebuild, audit the exact
   distribution, and run real-model production smoke before deployment.
7. After deployment, verify the explicit live URL, version/model/example
   hashes, links, privacy behavior, keyboard/accessibility path, and fixed-pair
   inference; record build, archive, URL, and rollback evidence.

Every step must be executed and recorded rather than inferred from local files.

For this maintenance release, the software version is `1.0.1` and the reused
model version remains `v1.0.0`. The verifier accepts that explicit mapping and
still requires new approval bound to the exact maintenance source commit and
all four unchanged evidence hashes. The old tag and approval cannot authorize
this candidate. The maintenance candidate contains no approval record.

## Rollback

Preserve every approved Pages artifact with a manifest and hash. If the live
release fails, redeploy the prior tagged artifact without retraining or
rebuilding dependencies, verify its model/version response, and record the
incident in `CHANGELOG.md` and `MONITORING_AND_FAILURES.md`. If no prior public
release exists, disable the link and use the recorded/local demo.

## Offline and outage fallback

The repository must reproduce a local static build. Preserve six annotated
screenshots, a recorded demo, the frozen result tables, and downloadable release
archive. These are availability fallbacks, not substitutes for a broken public
link at release review.

## Compatibility statement

Target current Chrome, Edge, and Firefox; use Playwright WebKit as automated
compatibility evidence. Do not claim Safari/iOS or phone performance without
physical-device testing. Reference-device and browser versions belong in the
release manifest.
