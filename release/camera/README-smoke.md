# Camera release smoke

This release-operations harness does not change the app. It checks the exact archived camera build from source `ca88b440636b8028e60a1e79ae6a51b0539a37ca`; never rebuild that artifact for this check. Running the HTTPS mode requires separate release authorization. The presence of this harness grants none.

## Configuration and command

Run from `web` using the already installed, locked dependencies:

```text
pnpm exec tsc -p ../release/camera/tsconfig.json
pnpm exec playwright test --config ../release/camera/playwright.live.config.ts
```

Set all three environment variables explicitly:

| Variable | Required value |
| --- | --- |
| `PLATEGAUGE_CAMERA_SMOKE_MODE` | `local` or `https`; there is no default |
| `PLATEGAUGE_CAMERA_SMOKE_INVENTORY` | Absolute regular-file path to the approved `inventory.json` |
| `PLATEGAUGE_CAMERA_SMOKE_ARTIFACTS` | Absolute, nonexistent diagnostics directory outside (and not an ancestor of) the checkout |

The destinations are fixed: local mode uses `http://127.0.0.1:4199/plategauge/`; HTTPS mode uses only `https://aldaqrouqtaysir.github.io/plategauge/`. There is no arbitrary host override. The config does not launch Vite or another server. For a local trial, first serve the independently verified, extracted archive on loopback port 4199. Do not serve a dev build or rebuild the archive. A missing mode, wrong inventory, unsafe/existing output path, or symlink ancestor stops before browser navigation. Even `--list` reserves a fresh diagnostics folder, so use another fresh path for the actual run. Do not set the internal ownership-nonce environment variable; it only coordinates config reloads within one invocation.

The inventory has strict shape `{schemaVersion:1, appSourceCommit:"ca88b440636b8028e60a1e79ae6a51b0539a37ca", files:[{path:"relative/POSIX",size:123,sha256:"lowercase64hex"}]}`. It contains exactly 46 sorted, unique, bounded paths. Its exact raw-byte SHA-256 is pinned to `64ef462efb059e6e6778934dae22a1b8f3fe28a0731d0b71f5ecf37d25b9fc80`. Structural validation also pins the unchanged model and frozen benchmark-evidence identities. The inventory digest must come from release approval, not a fresh download of a mutable live manifest.

## What is checked

Five checks comprise one non-browser preflight rejection test and four bounded Chromium flows: inert startup; generated before/after captures followed by explicit real pinned-model inference and optional mass arithmetic; explicit generated-session download/restore/clear; and navigation to evidence plus inert unknown/ambiguous routes. The product is not given a fake model. The test installs a synthetic camera before application code, then independently checks and locks that generated function before any camera action. It never calls native `getUserMedia`, requests permission, or uses personal images. A failed sentinel stops the test.

Every intercepted HTTP request must be a body-free, credential-free GET for an exact inventory path on the fixed origin. Only the named static-document query routes are allowed. WebSockets, redirects, cookie-setting responses, unexpected paths, other origins and write requests fail closed. Service workers are blocked. Responses are fetched from the actual server and their decoded bytes must match the inventory before browser execution. The proxy retains application/security/MIME headers; only transport length/encoding headers are removed to avoid double decompression. It does not substitute app, model or scientific bytes. This is a controlled-artifact verification proxy, not a general-purpose hostile-content streaming downloader: body size is checked after the response is buffered, in addition to a header bound.

Storage instrumentation and post-flow checks require no cookies, local/session storage, IndexedDB, upload calls, leftover active mock tracks or unreleased owned photo URLs. A session file exists only after the explicit download action; clearing browser state does not erase that downloaded unencrypted file. No saved estimate or authenticity claim is introduced.

The JSON report, failure traces and screenshots stay in the fresh diagnostics tree; all media is generated. There are no automatic retries. Preserve any failed run and use a new directory for a corrective rerun. A smoke run visits only assets used by these flows; the independent full-inventory verifier must separately verify all 46 archived and live assets. This smoke establishes functional behavior for generated pixels, not camera hardware quality, real-photo accuracy, field validation, calibration or inference performance.

## Rollback boundary

This camera profile deliberately fails if the previous benchmark-only artifact is served. Do not silently switch profiles to make a camera failure green. A separately authorized rollback must restore and verify the exact preceding approved benchmark archive, then use its existing benchmark-only public-smoke profile and separate pinned inventory. Retain the failed camera evidence and report which artifact is actually live. This harness does not publish, roll back, modify repository settings, or contact an external source outside its fixed target.
