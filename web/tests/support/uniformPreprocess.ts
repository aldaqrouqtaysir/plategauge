// Compatibility contract for the two synthetic, uniform resize fixtures.
// Exact geometry and the patterned no-resize fixture are checked separately.
const PIXELS = 224 * 224;
const MEANS = [0.485, 0.456, 0.406].map(Math.fround);
const STD = [0.229, 0.224, 0.225].map(Math.fround);

export function verifyUniformPreprocess(
  rgba: Uint8Array,
  tensorBytes: Uint8Array,
  color: readonly [number, number, number],
): { maxRgbDelta: number; maxTensorDelta: number; maxAlphaDelta: number; nonOpaquePixels: number } {
  if (rgba.length !== PIXELS * 4 || tensorBytes.length !== PIXELS * 3 * 4) {
    throw new Error("Unexpected fixture buffer size");
  }
  const tensor = new DataView(tensorBytes.buffer, tensorBytes.byteOffset, tensorBytes.byteLength);
  let maxRgbDelta = 0;
  let maxTensorDelta = 0;
  let maxAlphaDelta = 0;
  let nonOpaquePixels = 0;
  for (let pixel = 0; pixel < PIXELS; pixel++) {
    const alpha = rgba[4 * pixel + 3]!;
    // Hosted Linux WebKit returned 254 on 112 landscape pixels despite an
    // opaque canvas. Alpha is not a model input. Bound only this test-specific
    // readback difference; do not modify pixels or production preprocessing.
    if (alpha < 254) throw new Error("Uniform alpha must remain within 254–255");
    maxAlphaDelta = Math.max(maxAlphaDelta, 255 - alpha);
    if (alpha !== 255) nonOpaquePixels++;
    for (let channel = 0; channel < 3; channel++) {
      const byte = rgba[4 * pixel + channel]!;
      const rgbDelta = Math.abs(byte - color[channel]!);
      // One 8-bit level is the entire permitted rasterization budget. This is
      // not a model-output tolerance or a general image-parity claim.
      if (rgbDelta > 1) throw new Error("Uniform RGB drift exceeds one 8-bit level");
      const normalize = (value: number): number =>
        Math.fround(Math.fround(Math.fround(value / 255) - MEANS[channel]!) / STD[channel]!);
      const actual = tensor.getFloat32((channel * PIXELS + pixel) * 4, true);
      if (!Number.isFinite(actual) || actual !== normalize(byte)) {
        throw new Error("Tensor is not the exact CHW float32 normalization of observed pixels");
      }
      maxRgbDelta = Math.max(maxRgbDelta, rgbDelta);
      maxTensorDelta = Math.max(maxTensorDelta, Math.abs(actual - normalize(color[channel]!)));
    }
  }
  return { maxRgbDelta, maxTensorDelta, maxAlphaDelta, nonOpaquePixels };
}
