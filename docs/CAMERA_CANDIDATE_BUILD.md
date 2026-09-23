# Build and verify the experimental camera profile

`camera-experimental-r6` was published, deployed and live-verified on 23 September 2026.
See [current release status](CURRENT_RELEASE.md) for the exact source, prerelease
and checks. The historical benchmark and research results remain unchanged.
The package's existing `1.0.2` number is not the camera release identifier.

The [r6 presentation update](CAMERA_R6_RELEASE.md) simplifies capture guidance
without changing the model or workflow. Building a later checkout is not the
same as reproducing the deployed artifact.

## What is included

- A capture-first homepage and a separate, clearly labeled Evidence view.
- Explicit real-camera permission, before/after capture, framing reference,
  exact model-crop inspection, retakes, cancellation and clear/reset.
- Explicit on-device inference with the existing hash-pinned paired baseline.
  This model has **not** been validated for users' camera photos; the extension
  does not improve or replace its frozen accuracy results.
- Optional starting-mass conversion and explicitly downloaded, unencrypted
  Save session / Resume session files. There is no automatic photo storage.
- An optional local device-check report without photos, masses or predictions.

The synthetic camera is test infrastructure only. The built interface requests
the browser's camera only when the user chooses **Open camera**. Automated tests
do not open physical camera hardware.

## Reproduce a build

Use Node **22.20.0**, pnpm **11.19.0** and the unchanged lockfile. Follow the
[pinned-tool and clone setup](DEVELOPMENT.md#pinned-tools-and-checkout) first.
Run these shared commands from `web/` in a clean public checkout:

```powershell
pnpm install --frozen-lockfile
pnpm typecheck
pnpm lint
pnpm test:unit
pnpm exec playwright install chromium firefox webkit
```

On Linux, Playwright may also require OS libraries; see the
[browser setup notes](DEVELOPMENT.md#browser-tests).

Set the exact source identity, then build and test. PowerShell, from `web/`:

```powershell
$candidateRevision = git rev-parse HEAD
$env:VITE_SOURCE_URL = "https://github.com/aldaqrouqtaysir/plategauge/tree/$candidateRevision"
pnpm build:camera
pnpm test:camera-candidate
pnpm preview:camera
```

Bash, from `web/`:

```bash
export VITE_SOURCE_URL="https://github.com/aldaqrouqtaysir/plategauge/tree/$(git rev-parse HEAD)"
pnpm build:camera
pnpm test:camera-candidate
pnpm preview:camera
```

Open `http://127.0.0.1:4192/plategauge/`. The primary capture button leads to
`?capture=1`; Evidence uses `?view=evidence`. Merely opening either URL never
starts the camera or a prediction. The source link resolves publicly only
after the exact commit is published; a local commit is not a published release.
The browser test starts its own server on port 4198; the final preview command
is for manual inspection after tests finish. Stop it with Ctrl+C when finished.

These commands reproduce a source build, not necessarily the byte-identical
released distribution. That release uses a pinned prebuilt ZIP because HTML
newline bytes can differ across build platforms; see
[exact-artifact delivery](CAMERA_RELEASE.md#exact-artifact-delivery).

The test command requires installed Playwright Chromium, Firefox and WebKit
runtimes. `PLATEGAUGE_FIREFOX_EXECUTABLE` can select a documented compatible
Firefox executable. `PLATEGAUGE_CAMERA_CANDIDATE_ARTIFACTS` can keep diagnostic
artifacts outside the repository. No hardware permission is needed for these
synthetic browser tests.

Do not set `VITE_PLATEGAUGE_CAMERA_CANDIDATE` or
`VITE_PLATEGAUGE_TEST_MODEL` in the environment or environment files. The
explicit build mode alone selects the camera entry. Candidate/production
builds reject a test-model setting and explicitly compile that adapter off.
The candidate requires a credential-free, exact 40-character commit source URL.
Verify that it identifies the clean source actually used; URL syntax alone
cannot establish provenance.

## Keep the benchmark isolated

`pnpm build` still produces the benchmark in `dist/`; `pnpm build:camera`
produces the extension in `dist-camera/`. Neither a query string nor a normal
benchmark build enables camera capture. The original benchmark entry, model,
data, predictions, evidence and workflows are not replaced by this extension.
No development-server entry, synthetic capture route or test model is a
candidate product feature.

The camera entry requires a secure top-level page on loopback or the configured
GitHub Pages host. This restriction is not a substitute for publication
approval, a server anti-framing header, or scientific validation.

## Verification boundaries

Run and retain the complete unit and browser results, including failed attempts.
Browser checks cover generated before/after frames with the actual pinned ONNX
model, denied/late permission, cancellation, malformed session files, navigation
cleanup, explicit saving/resuming, request allowlisting, accessibility and small
viewports. Generated frames test software behavior, not estimation accuracy.

Verify default-build regression separately with `pnpm test:production`. Check
the immutable model hash, the frozen benchmark evidence verifier, the source
diff and all emitted assets. Rebuild using the final clean candidate commit;
record every output file's SHA-256 before considering publication. Diagnostic
traces or downloaded test sessions are not public assets.

Physical camera/phone compatibility, extended meal-delay behavior and model
accuracy on independent camera photographs remain unverified unless separately
documented. Do not infer them from headless browser tests or example predictions.

## Publication boundary

Running this guide does not push, tag, publish, deploy, introduce a better model
or validate public accuracy claims. The published camera tag and historical v1
tags are immutable. Any future release must identify its exact source and
verified build, preserve the benchmark and follow the
[current release process](CURRENT_RELEASE.md#operating-the-current-release). Changes on `main` do not automatically
deploy. Do not publish private research history.

See [the camera system card](CAMERA_SYSTEM_CARD.md) and
[privacy notice](CAMERA_PRIVACY_NOTICE.md). Automated checks do not establish
physical-device validation.
