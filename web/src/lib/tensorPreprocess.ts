const CROP_SIZE = 224;
const PLANE_SIZE = CROP_SIZE * CROP_SIZE;

// Math.fround at every operation mirrors NumPy's float32 pipeline instead of
// doing the whole expression in JavaScript float64 and rounding only once.
const MEANS = [Math.fround(0.485), Math.fround(0.456), Math.fround(0.406)] as const;
const DEVIATIONS = [Math.fround(0.229), Math.fround(0.224), Math.fround(0.225)] as const;

export function rgbaToNormalizedChw(rgba: Uint8ClampedArray): Float32Array {
  if (rgba.length !== PLANE_SIZE * 4) {
    throw new Error("Expected a 224×224 RGBA pixel buffer.");
  }
  const values = new Float32Array(3 * PLANE_SIZE);
  for (let pixel = 0; pixel < PLANE_SIZE; pixel += 1) {
    const rgbaOffset = pixel * 4;
    for (let channel = 0; channel < 3; channel += 1) {
      const byte = rgba[rgbaOffset + channel] ?? 0;
      const scaled = Math.fround(byte / 255);
      const centered = Math.fround(scaled - MEANS[channel]!);
      values[channel * PLANE_SIZE + pixel] = Math.fround(centered / DEVIATIONS[channel]!);
    }
  }
  return values;
}
