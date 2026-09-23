# Experimental camera release and rollback

This is a new delivery profile, not an amendment to historical Gate D evidence.
Its fixed application source is `ca88b440636b8028e60a1e79ae6a51b0539a37ca`.
The model, dataset, folds, predictions and scientific results are unchanged.
No physical-camera accuracy, food-waste reduction, independent applicant
reproduction or application-use claim is added.

## Identities and approval

- Application: the fixed source above and the 46 files in
  [the inventory](../release/camera/inventory.json).
- Operations: the reviewed descendant containing delivery code, checks and
  documentation, but no changed application or scientific files.
- Approval: a single child commit adding only `release/camera/approval.json`,
  after explicit user authorization. It binds both source identities, inventory,
  verification evidence, camera ZIP, rollback ZIP and rollback inventory.
- Release: a new `camera-experimental-r1` tag at that approval-only commit.
  Existing tags are never moved. The new release is an experimental prerelease.
- Destination: only `https://aldaqrouqtaysir.github.io/plategauge/`.

An approval JSON field is a record, not an authentication mechanism. The actual
user authorization, reviewed Git history, immutable release tag, restricted
workflow dispatch and GitHub Pages deployment permissions form the process.
Missing approval fails closed. See [the approval boundary](CAMERA_RELEASE_APPROVAL.md).

## Exact-artifact delivery

The release delivers the previously verified application bundle, not a fresh
Linux build. The original Windows build's HTML contains mixed source/Vite
newline conventions. A clean cross-platform rebuild can therefore differ in
bytes without changing behavior. We do not replace the approved hashes to make
another build pass. Source rebuilding remains useful for development, but its
output is not this frozen delivery artifact.

The deterministic ZIP contains sorted, uncompressed regular files with fixed
timestamps. It is stored as a release asset, not committed to Git. Delivery
checks the archive SHA-256 before extraction, exact member names and sizes,
every file hash, the pinned model, and the bundled notices. Traversal, duplicate
or case-colliding paths, links, extra members, oversized content, redirects and
unsafe extraction destinations are rejected.

The `Release experimental camera Pages` workflow is manually dispatched **at
the new tag**. It verifies approval before downloading release assets or
installing application dependencies, tests generated camera input with the
real pinned model on a local static server, and deploys that exact directory.
Only the deployment job receives Pages/id-token write permission. It then
compares every public file to the approved inventory and runs the browser
journey over HTTPS. No training, data acquisition or new model calibration occurs.

## Publication sequence

1. Finish local verifier, workflow, bundle, browser and secret-scan checks.
2. Obtain explicit authorization for the bounded experimental public release.
3. Freeze the operations commit; add the accurately dated approval-only record.
4. Verify the approval locally and create the new tag only if absent.
5. Push only the sanitized public lineage and that tag. Publish the prerelease
   with `camera-experimental-r1.zip` and `rollback-v1.0.2.zip` as named assets.
6. Dispatch `release-camera-pages.yml` with ref `camera-experimental-r1`.
7. Require success of both deployment and live verification. Inspect the visible
   page without activating hardware. Do not describe automated generated-input
   tests as a physical camera test.
8. Set repository variable `PLATEGAUGE_ACTIVE_PROFILE=camera-experimental-r1`
   only after successful live verification; run the new weekly check once.

The original benchmark workflow is unchanged except that its release-event
guard ignores this specific new tag. Its tag allowlist and Gate D checker are
not widened. A failed public check remains a failure; do not rewrite inventory
or silently accept whatever the live server returns.

## Rollback

The old approved `v1.0.2` distribution was recovered from workflow run
`35582218358`, artifact `10631275632` (`approved-static-dist-v1.0.2`). Its 36
files were compared byte-for-byte with the then-current live website before
release preparation. The original annotated tag object is
`0fdd88a8616c5925733f82d1b626f0de724776e2`, resolving to release commit
`b6a3c2519c78d83669444c31c7c139920a1c4506`; these are different identities.
The original approved source is `dc6abab7d94fb8332a7901b3b4a97ba25eb75fe3`.

The recovered files are repackaged without content changes into a separately
hashed release asset so recovery does not depend on an expiring Actions artifact.
The upstream Actions archive digest is provider metadata; the independently
verified claims are the recovered file hashes, live comparison, and new
deterministic ZIP hash in the bound records.

Dispatch `rollback-camera-pages.yml` at `camera-experimental-r1`. It validates
the approval and retrieves only the pinned rollback asset; recovery does not
depend on the camera ZIP remaining available. It deploys the original bytes,
then verifies all 36 public files. After success, set
`PLATEGAUGE_ACTIVE_PROFILE=v1.0.2` and manually run the original weekly smoke
workflow. Do not restore the camera profile until a separately justified fix.
No historical source, tag, model or evidence is rewritten.

## Monitoring and diagnostic privacy

The new weekly check runs only when the active profile equals
`camera-experimental-r1`. The older root smoke runs otherwise; documentation
link monitoring remains active in both states. Switching this routing variable
does not grant scientific or application authority.

Browser checks use generated drawings and explicitly replaced camera APIs,
never physical hardware or visitor files. Fresh contexts block service workers;
requests must be same-origin, GET-only, bodyless and on the trusted asset list.
Cookies, authorization headers and redirects are rejected. Reports are stored
outside the checkout. Workflows upload only machine-readable test reports, not
browser traces, screenshots, session files, or photos. Failed local attempts
remain distinguishable from successful reruns.

The local prepublication workflow cannot prove GitHub Actions or real-device
compatibility. Hosted execution and post-deployment checks are separate evidence.
