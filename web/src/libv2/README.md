# Pillow-compatible resize/crop helper

The experimental camera path uses this helper on the original camera-frame
pixels before JPEG preview encoding. It retains a 224px crop for an explicit
estimate request; reviewing a preview does not load a model. The estimator is
separate and permits only a local development context or the explicitly built,
secure camera candidate on its approved host. This helper itself does not load
models, access the camera, fetch files, or establish camera-estimation accuracy.

This module is separate from the fixed-example explorer's `lib/preprocess.ts`
Canvas pipeline. The port changes neither that pipeline nor the training
preprocessing or model artifact. Pixel-array equivalence below is not a claim
of image-decoder equivalence or real-world model validity.

## Interface

```ts
await resizeOpaqueRgbaBicubic({ width, height, data }, outputWidth, outputHeight, { signal });
await preparePillowCrop({ width, height, data }, { signal });
```

`data` must be a non-shared `Uint8ClampedArray` of exactly `width × height × 4` bytes, with alpha 255 for every pixel. Results use the same shape and own an independent buffer. The crop helper uses the existing model-card geometry: resize short edge to 256 with Python ties-to-even dimension rounding, then center-crop 224×224. It does not letterbox or normalize tensors.

`estimateResizeBudget` validates dimensions and returns a conservative private-allocation budget, exact scalar RGB multiply-add count, and pass order without allocating pixels. `pillowCropGeometry` validates the crop/resize budget. `PillowResizeError.code` identifies rejected dimensions, pixel counts, workspace/work budgets, buffers, alpha, or coefficients.

Limits are not caller-overridable: each dimension at most 16,384; input/output at most 16 million pixels; private workspace at most 128 MiB; at most 250 million RGB scalar multiply-adds. The workspace includes an input snapshot, pass outputs, and coefficient arrays/scratch; it excludes the caller's existing input and runtime/engine overhead. It is not an observed application-memory measurement.

The implementation yields after a bounded count of pixel-validation or resampling work, checks the supplied `AbortSignal`, and rejects cancellation with `AbortError`. Private intermediate pixels are zeroed on completion/error/cancellation. The returned successful result belongs to the caller and must be cleared when no longer needed. Input mutation during a yield cannot modify the private pixel snapshot. A synchronous input copy/individual bounded work batch is not interruptible mid-instruction.

## Algorithm and reference boundaries

The implementation follows Pillow 12.3.0's opaque RGB bicubic path: antialiased downsampling, pixel-center coefficients, clipped-edge renormalization, 22-bit coefficient quantization, and byte rounding/clipping after each axis. It also follows the Python `Image.resize` wrapper's vertical-first special case when the source is more than 100 times as tall as it is wide and its height is being reduced. See [the source and license notice](PILLOW_RESAMPLING_NOTICE.md).

It accepts pixels, not files. A future adapter must separately verify unscaled decoding, EXIF orientation, color conversion, transparent input behavior, cancellation, and cleanup. No claim about JPEG/WebP decoder equality, ICC profiles, translucent pixels, phones, model drift, real-image accuracy, or a new model's letterbox pipeline follows from synthetic pixel-array tests.

## Synthetic regression checks

`generatePillowGoldens.py` creates 93 deterministic opaque synthetic reference hashes using installed Pillow 12.3.0. `pillowResizeGoldens.json` records the generator identity. Existing goldens are not silently regenerated or overwritten; `--output` can write a fresh candidate file for review. Tests compare every output byte through exact SHA-256 equality—there is no tolerance—and cover up/downsampling, one-axis/identity resizes, boundary colors, patterns, crop dimension rounding, and the strict tall-image pass-order threshold. Additional guards test malformed/nonfinite dimensions, mismatched/shared buffers, alpha rejection, allocation/work refusal, cancellation, and snapshot ownership of pixels and source metadata.

These references are synthetic regression fixtures, not a research dataset or
photographs. They are generated from integer patterns, edge cases and uniform
colors. The tests load no model and change no scientific evidence. Historical
checks outside this repository are not required to run this self-contained
suite and are not claimed as independently reproduced by a repository user.
