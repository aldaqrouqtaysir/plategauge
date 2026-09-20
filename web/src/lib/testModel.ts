import type { PreparedImage, RawQuantiles } from "../types";

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function meanLuminance(image: PreparedImage): number {
  const bytes = new Uint8ClampedArray(image.rgba);
  let sum = 0;
  const pixelCount = bytes.length / 4;
  for (let index = 0; index < bytes.length; index += 4) {
    const red = bytes[index] ?? 0;
    const green = bytes[index + 1] ?? 0;
    const blue = bytes[index + 2] ?? 0;
    sum += 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  }
  return sum / (pixelCount * 255);
}

/**
 * Deterministic browser-test adapter. This is never enabled by a production build and its
 * result carries an explicit test warning so it cannot be mistaken for model evidence.
 */
export function createDeterministicTestPrediction(
  before: PreparedImage,
  after: PreparedImage,
): RawQuantiles {
  const beforeLuminance = meanLuminance(before);
  const afterLuminance = meanLuminance(after);
  const luminanceDifference = afterLuminance - beforeLuminance;
  const median = clamp(0.52 + luminanceDifference * 0.35);
  const halfWidth = Math.abs(luminanceDifference) > 0.45 ? 0.2 : 0.09;
  return {
    q05: clamp(median - halfWidth),
    q50: median,
    q95: clamp(median + halfWidth),
    modelVersion: "test-adapter/not-a-model",
    intervalGatePassed: false,
    abstentionWidth: 0.3,
    isTestAdapter: true,
    processingMs: 1,
  };
}
