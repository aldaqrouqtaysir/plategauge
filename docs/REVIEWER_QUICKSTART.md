# Five-minute reviewer quickstart

PlateGauge combines an experimental on-device camera workflow with a frozen
benchmark and failure explorer. It is not a scale replacement or evidence of
food-waste reduction. No raw dataset download or model training is needed.

[Open camera](https://aldaqrouqtaysir.github.io/plategauge/?capture=1) or
[open Evidence](https://aldaqrouqtaysir.github.io/plategauge/?view=evidence).
The live profile is `camera-experimental-r6`, deployed and live-verified on
23 September 2026. V1.0.2 remains the historical stable benchmark. See
[current release and checks](CURRENT_RELEASE.md).
The r6 update simplifies capture guidance while retaining the experimental
boundary and an expandable **Privacy & storage** explanation.
Choose either track below; using the camera is optional.

## Track A — try the experimental workflow

1. Read the camera instructions and limitation: camera-photo accuracy is
   unvalidated. Opening the page alone starts neither camera nor inference.
2. Choose **Open camera** only if you want to grant permission. Capture a
   before/after pair using the same single item, plate, framing and lighting.
   Keep people, documents and private details out of frame.
3. Review the model crops, then explicitly request an estimate. Leave starting
   mass blank unless you measured the initial net food mass; grams are a
   conversion from your input, not weight measured from photos.
4. Retake or clear the pair. Optional Save/Resume files remain local, but the
   downloaded file contains unencrypted photos and any entered mass. Clear
   does not delete downloaded copies.
5. Open **Evidence** and compare the frozen findings below. A convincing
   interaction or plausible estimate does not validate camera accuracy.

This is a workflow walkthrough, not a recorded physical-device test or accuracy
study. See the [privacy notice](CAMERA_PRIVACY_NOTICE.md) and
[camera system card](CAMERA_SYSTEM_CARD.md). To run this profile locally, use
the [camera build guide](CAMERA_CANDIDATE_BUILD.md).

## Track B — review the benchmark in five minutes

### Minute 1 — read the outcome

Read the README's **At a glance** and **What the evaluation found** sections.
The essential result is paired MobileNet macro-category MAE `0.122756` versus
`0.097858` for after-only MobileNet. The paired-image hypothesis failed.

### Minute 2 — verify the machine evidence

Open `reports/results.json` and confirm:

- `dataset.valid_pairs = 514` and `dataset.categories = 34`;
- paired MobileNet macro-category MAE `0.12275587386595668`;
- after-only MobileNet macro-category MAE `0.09785758682716902`; and
- `decisions.benchmark_only = true`.

`docs/RESULTS.md` explains the same values in prose. The bootstrap interval is
conditional on the fixed run; it is not a population or retraining guarantee.

### Minute 3 — inspect failures, not only the average

Open `docs/ERROR_ANALYSIS.md` and `docs/ROBUSTNESS.md`. The largest errors,
interior-target underestimation, confidently wrong cases, and after-image blur
breach explain the failed benchmark acceptance gates. The later camera workflow
uses that same paired baseline; it does not waive those failures, establish
camera accuracy or add calibrated intervals and reliable-abstention claims.

### Minute 4 — inspect the evidence workflow

The six screenshots in `reports/media/` preserve the historical fixed-example
journey. The current **Evidence** view still renders those frozen records, not
predictions for your camera photos. If the locked Python environment is already
installed, verify the browser evidence from the repository root with:

```text
uv run --locked python scripts/verify_web_benchmark_evidence.py verify --repo-root .
```

This checks the generated visible values and examples against canonical frozen
sources; it does not retrain or modify evidence. The released source also
uses path-specific line-ending rules to reconstruct the same evidence bytes on
default-Windows and LF-preserving checkouts; see
`docs/REPRODUCIBILITY_NOTE.md`.

### Minute 5 — check reproducibility and boundaries

Read `docs/MODEL_CARD.md` and `docs/DATASHEET.md`, then read
`docs/REPRODUCIBILITY_NOTE.md`. `docs/TEST_REPORT.md` records 209 passed Python
tests, one intentional skip, and `85.51%` coverage for the configured
**non-training Python scope**;
`model.py`, `training.py`, and `export.py` are excluded from that coverage
measurement and are validated through separate focused tests and artifact
checks. No user study, field validation, external-site validation, or phone
performance result exists. These historical counts are not the current camera
test totals; current release checks are linked in [the release overview](CURRENT_RELEASE.md).

## Creating new review media

For current commands, use the [media-generation guide](MAINTENANCE.md#new-screenshots-and-recordings),
not the command examples preserved with historical media. `pnpm capture:portfolio`
and `pnpm record:demo` are benchmark-only authoring tools, not camera demos.
Both require `--output` naming a new absolute directory outside the checkout;
they must not overwrite existing screenshots, recordings or provenance.
Review new media and its provenance before publishing. These tools do not test
physical cameras or establish model accuracy.
