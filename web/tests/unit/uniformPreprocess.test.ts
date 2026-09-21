import { describe, expect, it } from "vitest";
import { rgbaToNormalizedChw } from "../../src/lib/tensorPreprocess";
import { verifyUniformPreprocess } from "../support/uniformPreprocess";

const color = [17, 101, 233] as const;
function fixture(delta = 0): { rgba: Uint8Array; tensor: Uint8Array } {
  const pixels = new Uint8ClampedArray(224 * 224 * 4);
  for (let i = 0; i < pixels.length; i += 4) pixels.set([...color, 255], i);
  pixels[0] = color[0] + delta;
  return { rgba: new Uint8Array(pixels), tensor: new Uint8Array(rgbaToNormalizedChw(pixels).buffer) };
}

describe("WebKit uniform fixture compatibility budget", () => {
  it.each([-1, 0, 1])("accepts %i level with exact normalization", (delta) => {
    const { rgba, tensor } = fixture(delta);
    expect(verifyUniformPreprocess(rgba, tensor, color).maxRgbDelta).toBe(Math.abs(delta));
  });
  it.each([-2, 2])("rejects %i levels", (delta) => {
    const { rgba, tensor } = fixture(delta);
    expect(() => verifyUniformPreprocess(rgba, tensor, color)).toThrow("one 8-bit level");
  });
  it("rejects alpha drift, channel swaps, and wrong size", () => {
    const { rgba, tensor } = fixture();
    rgba[3] = 254;
    expect(() => verifyUniformPreprocess(rgba, tensor, color)).toThrow("opaque");
    rgba[3] = 255;
    [rgba[0], rgba[1]] = [rgba[1]!, rgba[0]!];
    expect(() => verifyUniformPreprocess(rgba, tensor, color)).toThrow("one 8-bit level");
    expect(() => verifyUniformPreprocess(rgba.subarray(4), tensor, color)).toThrow("buffer size");
  });
  it.each([Number.NaN, Number.POSITIVE_INFINITY, 0])("rejects invalid or wrong tensor values (%s)", (value) => {
    const { rgba, tensor } = fixture();
    new DataView(tensor.buffer).setFloat32(0, value, true);
    expect(() => verifyUniformPreprocess(rgba, tensor, color)).toThrow("exact CHW");
  });
});
