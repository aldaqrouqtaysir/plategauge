# PlateGauge

**Capture a before-and-after pair. Explore the evidence behind the estimate.**

[Open camera](https://aldaqrouqtaysir.github.io/plategauge/?capture=1) ·
[Explore the evidence](https://aldaqrouqtaysir.github.io/plategauge/?view=evidence) ·
[Benchmark results](docs/RESULTS.md) ·
[Five-minute walkthrough](docs/REVIEWER_QUICKSTART.md) ·
[Run locally](docs/DEVELOPMENT.md)

PlateGauge combines a browser-local experimental camera workflow with an
interactive computer-vision benchmark. Capture a single food item before and
after, review the model's crop, and explicitly request an experimental estimate.
Then explore the frozen evaluation to see where the model succeeds and fails.
**Camera-photo accuracy has not been validated; this is not a food scale.**

The [r6 camera maintenance release](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/camera-experimental-r6)
is published, deployed and live-verified on 23 September 2026. The frozen benchmark remains
available under **Evidence**. See [current release and verification](docs/CURRENT_RELEASE.md).
The [presentation update](docs/CAMERA_R6_RELEASE.md) simplifies capture guidance
without changing the model or workflow.

![Historical r1 capture-first homepage, with the camera off](reports/media/camera-home-2026-09-23.png)

Historical `camera-experimental-r1` interface captured on 23 September 2026,
not the current r6 layout. The illustrated pair is not a photograph or model
output. [Historical screenshot provenance and idle camera view](reports/media/CAMERA_SCREENSHOTS_2026-09-23.md) ·
[Current release and interface](docs/CURRENT_RELEASE.md).

## Explore the project

- **Capture and compare:** the experimental camera profile supports real camera
  capture, crop review, optional starting mass, and explicit local session files.
  Opening the page does not turn on the camera or run the model.
- **Compare models:** paired and after-only MobileNet, handcrafted baselines,
  and heavier vision-model references under a documented evaluation protocol.
- **Inspect evidence:** browse licensed fixed examples alongside frozen
  predictions, reference fractions, and errors.
- **Understand failures:** examine target-range disparities, category shift,
  robustness checks, and the limits of uncertainty estimates.
- **Trace the results:** follow visible values back to versioned reports,
  manifests, model checksums, and automated integrity checks.

There are two separately guarded release profiles. Historical
[v1.0.2](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/v1.0.2)
is a **fixed-example benchmark and failure explorer**. The
[`camera-experimental-r6`](https://github.com/aldaqrouqtaysir/plategauge/releases/tag/camera-experimental-r6)
prerelease adds the experimental camera workflow and keeps the benchmark under
**Evidence**. Changes on `main` do not automatically deploy. See the
[current release and rollback guide](docs/CURRENT_RELEASE.md#operating-the-current-release). Neither profile needs a
raw-dataset download, training, an account, or paid infrastructure to use.

## At a glance

| Research and engineering | Implementation |
|---|---|
| Task | Fraction of a single food item remaining in standardized before/after photographs |
| Benchmark | 514 valid LeFood-Set v1 pairs, 34 food categories |
| Evaluation | Duplicate-safe, category-disjoint nested cross-validation |
| Compact model | Shared MobileNetV3-Small encoder, paired feature fusion, ordered quantile head |
| Browser stack | React, TypeScript, Web Worker, ONNX Runtime Web/WASM |
| Model artifact | 10.36 MB FP32 ONNX, SHA-256 verified |
| Privacy | No visitor uploads, accounts, analytics, or application database |

## What the evaluation found

Lower macro-category mean absolute error (MAE) is better. Fractions run from
zero to one; an MAE of `0.10` is ten percentage points of leftover fraction.

| Model | Macro-category MAE |
|---|---:|
| After-only MobileNet | **0.0979** |
| Paired MobileNet | 0.1228 |
| Handcrafted features + Ridge | 0.2515 |

The paired model beat the handcrafted baseline, but **adding the before image
did not improve on after-only MobileNet** in this protocol. The paired-minus-
after-only difference was `+0.0249`, with a category-bootstrap 95% interval of
`[0.0077, 0.0437]`. This interval is conditional on the frozen folds, seed,
recipes, and predictions; it does not measure uncertainty across retraining
or real-world populations.

The dataset is endpoint-heavy: 254 of 514 records (`49.4%`) are exactly empty
or exactly full. Interior target ranges are harder. The paired model did not
meet the predefined numeric-demo, interval, useful-abstention, or robustness
criteria. The historical benchmark therefore offers no visitor-image estimates.
The separately gated camera experiment uses the **same model**, not a promoted
or improved one. Its new-photo estimates are unvalidated experimental outputs;
camera functionality does not change or waive the benchmark findings.

See the [full results and acceptance criteria](docs/RESULTS.md),
[machine-readable results](reports/results.json),
[error analysis](docs/ERROR_ANALYSIS.md), and
[robustness report](docs/ROBUSTNESS.md).

## How it works

The research model uses the same visual encoder for both images, then fuses
their embeddings, absolute difference, and elementwise product. Its target is:

```text
leftover_fraction = recorded_weight_after / recorded_weight_before
```

The benchmark renders precomputed evidence. In the camera profile, inference
runs only after explicit confirmation, using a hash-checked ONNX model inside
a browser worker. Photos are processed on-device and are not uploaded.
Optional grams are calculated from a starting mass supplied by the user—not
weighed from a photograph. See the [camera system card](docs/CAMERA_SYSTEM_CARD.md),
[historical benchmark system card](docs/SYSTEM_CARD.md), and
[model card](docs/MODEL_CARD.md).

## Run locally

For the camera experience shown on the live site, follow the
[camera build and verification guide](docs/CAMERA_CANDIDATE_BUILD.md).
The short development path below starts the **benchmark profile**, not the camera:

Use Node.js 22 and the repository-pinned `pnpm@11.19.0`:

```sh
git clone https://github.com/aldaqrouqtaysir/plategauge.git
cd plategauge/web
pnpm install --frozen-lockfile
pnpm dev --host 127.0.0.1
```

Open the local URL printed by Vite. For dependency setup, lint/type checks,
unit tests, production builds, and browser verification, see the
[development guide](docs/DEVELOPMENT.md). Building the website does not require
the raw LeFood dataset, model training, or paid services.

## Experimental camera profile

This checkout includes a separately built capture-first camera profile: real
before/after camera capture, model-crop review, explicit on-device estimation,
and optional Save session / Resume session files. Photos are not uploaded or
automatically saved. The unchanged paired baseline supplies the experimental
estimate; this is **not a new model or validation for camera photos**.

The ordinary build remains the benchmark described above; it is not the
currently deployed camera profile.
Use the [camera build guide](docs/CAMERA_CANDIDATE_BUILD.md) for the separately
enabled local build, its tests and publication boundary. Its
[system card](docs/CAMERA_SYSTEM_CARD.md) and
[privacy notice](docs/CAMERA_PRIVACY_NOTICE.md) describe that extension only.

## Scope and limitations

This study uses one controlled Indonesian hospital acquisition setup. It does
not establish accuracy for arbitrary meals, uncontrolled phone photography,
UAE cuisines, or other institutions. PlateGauge does not identify foods,
estimate nutrition, replace a scale, support clinical decisions, or claim
measured food-waste reduction.

The benchmark does not accept visitor images. Camera photos stay in browser
memory unless the user explicitly downloads a session file; that file contains
unencrypted photos and any entered mass. GitHub Pages and the visitor's network
may still process ordinary request metadata; see the
[camera privacy notice](docs/CAMERA_PRIVACY_NOTICE.md) and
[historical benchmark privacy notice](docs/PRIVACY_NOTICE.md). Browser timing measurements apply
only to the documented reference laptop, not unmeasured phones or devices.

## Repository map

```text
src/plategauge/       Python data, models, training, evaluation, and export
web/                 React/TypeScript camera workflow, evidence explorer, tests
release/camera-r6/   R6 exact-bundle delivery, approval checks, smoke tests
configs/             Frozen experiment configurations
data/                Manifests and provenance; raw data stays outside Git
tests/               Python and integrity tests
reports/             Frozen results, figures, and release evidence
docs/                Methods, cards, development, and project records
.github/workflows/   CI, guarded releases, and monitoring
```

## Further reading

- [Evaluation protocol](docs/EVALUATION_PROTOCOL.md) and [research decisions](docs/RESEARCH_DECISIONS.md)
- [Datasheet](docs/DATASHEET.md), [data licenses](docs/DATA_LICENSES.md), and [reproducibility note](docs/REPRODUCIBILITY_NOTE.md)
- [Claim-evidence map](docs/CLAIM_EVIDENCE_MAP.csv)
- [Current release](docs/CURRENT_RELEASE.md), [release history](CHANGELOG.md), and [monitoring](docs/MONITORING_AND_FAILURES.md)
- [Maintenance audit and repairs](docs/MAINTENANCE_AUDIT_2026-09-23.md)
- [Maintainer checks and dependency updates](docs/MAINTENANCE.md), and [research utility erratum](docs/RESEARCH_UTILITY_ERRATA.md)
- [Contributing](CONTRIBUTING.md) and [security](SECURITY.md)

Source code is [Apache-2.0](LICENSE). LeFood-Set v1 and the dataset-derived
trained artifact carry CC BY 4.0 attribution and change notices; see [NOTICE](NOTICE).
Historical release records describe their dated state, not the status of every
later checkout. Released scientific evidence, model identity (`v1.0.0`), and
existing release tags are unchanged by the separate camera release.
