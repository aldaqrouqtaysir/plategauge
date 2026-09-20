import { describe, expect, it } from "vitest";
import type { PreparedImage } from "../types";
import { createDeterministicTestPrediction } from "./testModel";

function solidImage(red: number, green: number, blue: number): PreparedImage {
  const pixels = new Uint8ClampedArray(224 * 224 * 4);
  for (let index = 0; index < pixels.length; index += 4) {
    pixels[index] = red;
    pixels[index + 1] = green;
    pixels[index + 2] = blue;
    pixels[index + 3] = 255;
  }
  return { width: 224, height: 224, rgba: pixels.buffer };
}

describe("test model adapter", () => {
  it("is deterministic, ordered, bounded, and unmistakably labeled", () => {
    const before = solidImage(240, 240, 240);
    const after = solidImage(80, 80, 80);
    const first = createDeterministicTestPrediction(before, after);
    const second = createDeterministicTestPrediction(before, after);
    expect(first).toEqual(second);
    expect(first.modelVersion).toMatch(/test-adapter/);
    expect(first.isTestAdapter).toBe(true);
    expect(first.q05).toBeGreaterThanOrEqual(0);
    expect(first.q05).toBeLessThan(first.q50);
    expect(first.q50).toBeLessThan(first.q95);
    expect(first.q95).toBeLessThanOrEqual(1);
  });

  it("clamps very bright differences to a valid interval", () => {
    const output = createDeterministicTestPrediction(
      solidImage(0, 0, 0),
      solidImage(255, 255, 255),
    );
    expect(output.q95).toBeLessThanOrEqual(1);
  });
});
