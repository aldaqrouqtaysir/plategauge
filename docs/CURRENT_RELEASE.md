# Current release

The camera release combines explicit on-device capture and estimation with
the unchanged benchmark and failure explorer. The
[camera-experimental-r3 update](CAMERA_R3_RELEASE.md) refines responsive metric
spacing, integrates evaluation context into the relevant sections and retires
an obsolete presentation resource. Its
release-specific workflow records publication and live verification;
main-source changes do not deploy automatically. The r1/r2 identities and
verification records remain historical, not the new r3 artifact identities.

[Open camera](https://aldaqrouqtaysir.github.io/plategauge/?capture=1) ·
[Explore evidence](https://aldaqrouqtaysir.github.io/plategauge/?view=evidence) ·
[Five-minute walkthrough](REVIEWER_QUICKSTART.md) ·
[Build locally](CAMERA_CANDIDATE_BUILD.md)

## What is available

- Real before/after camera capture, model-crop review, retakes and clear/reset.
- Explicit inference in a browser worker using the existing hash-checked ONNX
  model; photos, starting mass and estimates are not uploaded.
- Optional starting-mass conversion and explicitly saved/resumed local session
  files. These files contain unencrypted photos; nothing is saved automatically.
- A separately labeled Evidence view with frozen results and licensed examples.
- An optional local device-check export containing metadata, not photos,
  masses or predictions. It is a self-report, not certification.

Camera-photo accuracy is **not validated**. The model is unchanged, and its
failed benchmark acceptance gates remain intact. This release does not establish
food-weight accuracy, operational usefulness or food-waste reduction. It is not
for medical, nutritional, purchasing or safety decisions.

## Current identities and observed checks

| Component | Identity / observation |
|---|---|
| Published prerelease | [camera-experimental-r3](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/camera-experimental-r3) |
| Frozen app source | `62efadcfd342a193458036912b38b0a613bf94be` |
| Tag / approval commit | `089b91e7f301453bc5753f5aa601d6340b10bde5` |
| Exact distribution | [45-file inventory](../release/camera-r3/inventory.json); SHA-256 `ddf3fd89a19aa2032bec60ab16a9a52decfc59be782dc73df04d093dd6f524f3` |
| [Deployment and live verification 35893477387](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35893477387) | Passed: exact archive and 45 live files; six local and six HTTPS checks |
| [R3 weekly smoke 35894343530](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35894343530) | Passed after `PLATEGAUGE_ACTIVE_PROFILE=camera-experimental-r3` was selected |
| [Source CI 35893340197](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35893340197) | Passed for `cb3a3b310658eb25d5cf94c0aa118b3ae4446ef2`; dependency review inapplicable to push |

These are dated observations from 23 September 2026, not guarantees about future
runs. The source-only assertion correction after the app freeze did not rebuild
or change the served artifact. Current checks use generated camera frames, not
physical-device or independent measured-mass validation.

## Operating the current release

The active workflow is `weekly-camera-r3-smoke.yml`, pinned to the published r3
tag. To verify that release, run it without changing its inventory or source.
`release-camera-r3-pages.yml` delivers only the approved r3 archive when dispatched
at `camera-experimental-r3`; it never rebuilds from `main`.

If a justified recovery is needed, dispatch `rollback-camera-r3-pages.yml` at
that same tag. It verifies and restores the unchanged 36-file `v1.0.2` benchmark
archive. Only after its live verification succeeds, select
`PLATEGAUGE_ACTIVE_PROFILE=v1.0.2` and run `weekly-smoke.yml`. Preserve the failed
camera evidence. A rollback changes which product is live, not its scientific
claims. These instructions do not initiate or authorize a recovery by themselves.

For a new release, prepare a new source, operations directory, approval-only
record and tag; do not mutate the published ones. The
[r3 artifact record](CAMERA_R3_RELEASE.md) and
[smoke contract](../release/camera-r3/README-smoke.md) bind the current delivery.
The [r1 procedure](CAMERA_RELEASE.md) is historical context, not a command list
for today's profile. See [maintenance](MAINTENANCE.md) for safe source changes.

## R1 baseline identities (preserved)

| Component | Identity |
|---|---|
| Frozen application source | `ca88b440636b8028e60a1e79ae6a51b0539a37ca` |
| Reviewed release operations | `94f8c14f850490ad81da221a7d6454f569f1b02a` |
| Immutable camera release commit | `ef769694b15a4333787946b5e971a6987cf5334e` |
| Camera tag | `camera-experimental-r1` |
| Model SHA-256 | `9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675` |
| Published inventory | [46-file inventory](../release/camera/inventory.json) |

The release contains the exact prebuilt bundle, not a later build from `main`.
Main-source maintenance does not deploy automatically or move release tags.
The later import-only correction `4f6bb44f27bb7185393cdc856bbd6fb0e8ca6f5b`
affected a development fixture generator, not the deployed files.

[v1.0.2](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/v1.0.2)
remains the latest stable **benchmark-only** release and the preserved rollback
target. The camera prerelease does not rename it or change its evidence.

## Original r1 engineering evidence (preserved)

| Check | Recorded result |
|---|---|
| [Release run 35847456472](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35847456472) | Passed: five predeployment tests, five HTTPS tests and all 46 published file hashes |
| [First weekly camera check 35847916308](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35847916308) | Five smoke tests passed |
| [Source CI 35848168116](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35848168116) | Passed after the import-only correction; push-inapplicable dependency review was skipped |
| [Documentation links 35848362866](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35848362866) | Failed: 99/100 occurrences passed; one external MDPI HTTP 403 remains unresolved |

These are dated observations, not promises about later runs. Automated camera
tests use generated frames with the unchanged model; they do not establish
physical-camera compatibility, phone performance or accuracy on new photos.
No user study, independent measured-mass camera validation or applicant-performed
independent reproduction is established.

## Reading historical documents

The model, data, benchmark cards, research reports and historical media describe
their frozen checkpoints. The historical r1/r2 copies of the camera system card
and privacy notice remain byte-for-byte unchanged in their release artifacts.
The current system card omits the former development-workflow paragraph; its
model identity, input requirements and scientific limitations are unchanged.

For practical use, start with the [reviewer guide](REVIEWER_QUICKSTART.md),
[camera privacy notice](CAMERA_PRIVACY_NOTICE.md) and
[security policy](../SECURITY.md). For maintenance, use the
[current operating guide](#operating-the-current-release), [monitoring record](MONITORING_AND_FAILURES.md)
and [change history](../CHANGELOG.md). Source builds and research reproduction
are different activities; the [development guide](DEVELOPMENT.md) keeps them separate.
