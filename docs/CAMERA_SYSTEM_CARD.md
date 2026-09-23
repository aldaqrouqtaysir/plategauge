# Camera experimental candidate — system card

Candidate ID: `camera-experimental-r1`. This is release preparation, not a claim
that the candidate has been published or validated for real-world use.

## Purpose and flow

An adult researcher or curious reviewer can capture a standardized before/after
pair of one food item, inspect the exact model crop, and explicitly request an
experimental leftover-fraction estimate. The same plate, item, framing, distance
and lighting are required. Optional remaining grams equal the predicted fraction
times an initial net food mass entered by the user; the photos do not measure grams.

Browser camera → bounded sRGB frame → deterministic 224px model crop → dedicated
worker → hash-pinned ONNX model → experimental result. No upload/API path exists.
Camera permission, inference, session saving and device-report download each
require an explicit user action. Selecting a route does not activate a camera.

The homepage makes capture the primary workflow. The evidence route still
exposes the original frozen research benchmark, separately labeled as not
validation of camera estimates. Unknown/ambiguous URLs fall back to the homepage.
Synthetic capture fixtures and test models are not candidate product routes.

## Model and scientific boundary

The existing paired v1 baseline is unchanged:

- Model file: `models/plategauge.onnx`, 10,355,122 bytes.
- SHA-256: `9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675`.
- Session/model identity: `v1.0.0-paired-baseline/experimental-camera-r1`.
- No new fitting, quantization, calibration, model promotion or revised evaluation.

This baseline failed the historical public numeric-demo acceptance gate and
did not outperform after-only inference in the frozen study. It can produce
substantially wrong estimates for user photos. The experimental camera scope
does not reverse that result or establish usefulness, robustness, general
food/cuisine validity, or food-waste reduction. No confidence intervals or
reliable abstention claims are shown. All recorded research values stay intact.

Capture cropping uses the separately tested opaque-RGB Pillow-compatible
resampler; it does not silently replace the frozen benchmark preprocessing.
Synthetic pixel parity is not camera-decoder or real-image accuracy validation.
Its separate attribution is in `PILLOW_RESAMPLING_NOTICE.md` in the bundled notices.

## Engineering controls and residual risks

- Secure top-level contexts only: configured GitHub Pages host or loopback.
  Other hosts, insecure contexts and embedded frames fail closed. This is a
  runtime restriction, not an HTTP anti-framing-header claim.
- No microphone, automatic camera activation, cloud inference, telemetry or
  persistent browser photo store. Explicit downloaded files remain outside
  the app's deletion control.
- Bounded image dimensions/work, input shape validation, model byte/hash checks,
  request cancellation, worker termination and owned-buffer cleanup.
- Same-origin static assets and restrictive CSP. ORT's internal runtime loading
  remains a third-party dependency; browser CSP is part of that boundary.
- A photo is not proof that the same food/plate or viewing conditions were used.
  Crop overlays aid framing but do not validate alignment or detect misuse.
- No food recognition or rejection of non-food scenes is promised. The user
  must respect the single-item input regime. Mixing foods invalidates the scope.
- Session checksums catch corruption, not malicious edits or forged provenance.

## Verification and release status

Candidate testing uses synthetic camera frames and existing pinned model
inference, not newly collected user data. Automated Chrome/Firefox/WebKit and
responsive-layout tests do not establish physical camera/phone behavior.
Named-device camera permission, meal-delay and memory observations remain
separate from automated checks and from an independent measured-mass study.

The candidate is built separately into `dist-camera`; the default benchmark
build remains isolated. Existing Pages workflows and immutable v1 tags are not
changed. Publication requires a separate exact-source/build decision; passing
tests alone neither deploys it nor authorizes public accuracy claims.

The extension uses the existing AI-assisted engineering workflow. No independent
applicant reproduction, physical-device testing, or independent implementation
claim is inferred from these automated results.
