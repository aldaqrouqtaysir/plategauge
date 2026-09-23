# Current release

The camera release combines explicit on-device capture and estimation with
the unchanged benchmark and failure explorer. The footer-only
[camera-experimental-r2 update](CAMERA_R2_RELEASE.md) removes two Evidence-footer
paragraphs while retaining their linked documentation. Its release-specific
workflow records publication and live verification; main-source changes do
not deploy automatically. The r1 identities and original verification below
remain historical records, not the new r2 artifact identities.

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
their frozen checkpoints. The bundled camera system card and privacy notice
were frozen before publication, so their candidate-stage language is retained
byte-for-byte. This overview records subsequent publication without rewriting
those artifacts or their claims.

For practical use, start with the [reviewer guide](REVIEWER_QUICKSTART.md),
[camera privacy notice](CAMERA_PRIVACY_NOTICE.md) and
[security policy](../SECURITY.md). For maintenance, use the
[release/rollback guide](CAMERA_RELEASE.md), [monitoring record](MONITORING_AND_FAILURES.md)
and [change history](../CHANGELOG.md). Source builds and research reproduction
are different activities; the [development guide](DEVELOPMENT.md) keeps them separate.
