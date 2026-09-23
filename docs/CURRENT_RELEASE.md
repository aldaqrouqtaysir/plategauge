# Current release

The camera release combines explicit on-device capture and estimation with
the unchanged benchmark and failure explorer. The
[camera-experimental-r6 maintenance release](CAMERA_R6_RELEASE.md) simplifies
capture guidance and groups longer privacy/storage details in an accessible
disclosure. Experimental-estimate and unencrypted-file warnings remain beside
the relevant actions; capture, inference and the model are unchanged. The prerelease
is published, deployed and live-verified on 23 September 2026. Main-source changes
do not deploy automatically. Earlier release records, including undeployed r4,
remain historical; the r6 observations below identify the current artifact.

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
| Published prerelease | [camera-experimental-r6](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/camera-experimental-r6) |
| Frozen app source | `d2fc03257e8ebfdae3923aa454fa8b3645212731` |
| Reviewed release operations | `efa45fa6be6bddc5092282635761bd38af77c840` |
| Tag / approval commit | `6154dc0870be3387525811551aa5858665eac447` |
| Annotated tag object | `f63bcdbcd61847fa7ea2cefa5892d53f5f3ee85c` |
| Exact distribution | [45-file inventory](../release/camera-r6/inventory.json); SHA-256 `a95a1770aaae2373887fd3bc38d8adcd8f9f856c6b02c41bd92ebec3f68c2fc8` |
| Camera ZIP SHA-256 | `b4d8dba94790881b434796769f9735932f2ae0cf0e7e7acf12638530a6098c96` |
| [Bound local verification](../release/camera-r6/verification-evidence.json) | SHA-256 `cdc6de18fc76fc6b3b3f3dd31a446dcae6e2b1663f0621adedeb2d40be40d0d3` |
| Local checks | 779 unit, 72 browser, eight exact-archive and 44 release-verifier checks passed; earlier failed attempts are retained |
| [R6 source CI 35905290466](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35905290466) | Passed for `efa45fa6be6bddc5092282635761bd38af77c840`; all applicable jobs succeeded |
| [Release workflow 35905487398](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35905487398) | Passed: predeployment verification, deployment, all 45 live-file hashes and eight HTTPS-mode harness checks |
| Active monitoring profile | `PLATEGAUGE_ACTIVE_PROFILE=camera-experimental-r6` |
| [R6 weekly smoke 35906209889](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35906209889) | Passed after r6 profile selection: all 45 live-file hashes and eight HTTPS-mode harness checks |

These are dated observations from 23 September 2026, not guarantees about future
runs. Publication, deployment and weekly monitoring are distinct checks. Current checks use
generated camera frames, not physical-device or independent measured-mass
validation. The model and frozen scientific evidence remain unchanged.

## Operating the current release

The active profile is `PLATEGAUGE_ACTIVE_PROFILE=camera-experimental-r6`.
Run `weekly-camera-r6-smoke.yml` to verify it against the published r6 tag.
Do not change the profile to hide a failed check.
`release-camera-r6-pages.yml` delivers only the approved r6 archive when dispatched
at `camera-experimental-r6`; it never rebuilds from `main`.

If a justified recovery of the deployed r6 profile is needed, dispatch `rollback-camera-r6-pages.yml` at
that same tag. It verifies and restores the unchanged 36-file `v1.0.2` benchmark
archive. Only after its live verification succeeds, select
`PLATEGAUGE_ACTIVE_PROFILE=v1.0.2` and run `weekly-smoke.yml`. Preserve the failed
camera evidence. A rollback changes which product is live, not its scientific
claims. These instructions do not initiate or authorize a recovery by themselves.

For a new release, prepare a new source, operations directory, approval-only
record and tag; do not mutate the published ones. The
[r6 artifact record](CAMERA_R6_RELEASE.md) and
[smoke contract](../release/camera-r6/README-smoke.md) bind the r6 delivery.
The [r1 procedure](CAMERA_RELEASE.md) is historical context, not a command list
for today's profile. See [maintenance](MAINTENANCE.md) for safe source changes.

## R5 identities and observed checks (preserved)

| Component | Identity / observation |
|---|---|
| Published prerelease | [camera-experimental-r5](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/camera-experimental-r5) |
| Frozen app source | `40493849af148124a45b6a6c65d9c9146c03fdb4` |
| Reviewed release operations | `4acd818be4dd8c071a24beb03cf65ce89d555001` |
| Tag / approval commit | `cc09cf7ff65eff6f07a9df60b9e629d1a69dfe9f` |
| Annotated tag object | `0c36c3b2c2cefbf75144586a75c93d2a37b9fe68` |
| Exact distribution | [45-file inventory](../release/camera-r5/inventory.json); SHA-256 `4f187ffba720de77cc2349d1fcdbd2b29d03c131aac132006b036fc8514e57e5` |
| [Bound local verification](../release/camera-r5/verification-evidence.json) | SHA-256 `a457f8433be2ea164f19d608e2e37562b46d8f45e3be325ccd8c616de35afb5e` |
| [R5 source CI 35899982443](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35899982443) | Passed for `4acd818be4dd8c071a24beb03cf65ce89d555001`; all applicable jobs succeeded |
| [Release workflow 35900187059](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35900187059) | Passed: predeployment verification, deployment, all 45 live-file hashes and eight HTTPS checks |
| Active monitoring profile | `PLATEGAUGE_ACTIVE_PROFILE=camera-experimental-r5` |
| [R5 weekly smoke 35901135854](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35901135854) | Passed after r5 profile selection: all 45 live-file hashes and eight HTTPS checks |

These are the recorded r5 observations from 23 September 2026, before r6 replaced
it. They do not describe the current active profile or guarantee later checks.

## R4 published but not deployed — preserved

[camera-experimental-r4](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/camera-experimental-r4)
remains an immutable prerelease. Its [protected release verification 35898553111](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35898553111)
passed seven checks and timed out waiting for the modified Privacy Markdown-link
popup on Linux. Deployment and live verification were skipped; r3 stayed live.
The platform cause is not conclusively established. R5 tests the existing HTML
Evidence link without changing the audited app code or weakening the network
checks. See the [r4 artifact record](CAMERA_R4_RELEASE.md) and
[r5 successor explanation](CAMERA_R5_RELEASE.md).

R4 app-source [CI 35897686057](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35897686057)
and operations [CI 35898359826](https://github.com/aldaqrouqtaysir/plategauge/actions/runs/35898359826)
passed. Neither result overrides the failed deployment prerequisite. Its tag,
archive and failed verification remain unchanged.

## R3 identities and observed checks (preserved)

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
