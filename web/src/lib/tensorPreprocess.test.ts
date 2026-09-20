import { describe, expect, it } from "vitest";
import { rgbaToNormalizedChw } from "./tensorPreprocess";

describe("rgbaToNormalizedChw", () => {
  it("uses CHW order and explicit float32 arithmetic", () => {
    const rgba = new Uint8ClampedArray(224 * 224 * 4);
    for (let pixel = 0; pixel < 224 * 224; pixel += 1) {
      rgba[pixel * 4] = 255;
      rgba[pixel * 4 + 1] = 128;
      rgba[pixel * 4 + 2] = 0;
      rgba[pixel * 4 + 3] = 255;
    }
    const tensor = rgbaToNormalizedChw(rgba);
    const plane = 224 * 224;
    expect(tensor).toHaveLength(plane * 3);
    expect(tensor[0]).toBe(Math.fround(Math.fround(1 - Math.fround(0.485)) / Math.fround(0.229)));
    expect(tensor[plane]).toBe(
      Math.fround(
        Math.fround(Math.fround(128 / 255) - Math.fround(0.456)) / Math.fround(0.224),
      ),
    );
    expect(tensor[plane * 2]).toBe(
      Math.fround(Math.fround(0 - Math.fround(0.406)) / Math.fround(0.225)),
    );
  });

  it("rejects any non-224 RGBA buffer", () => {
    expect(() => rgbaToNormalizedChw(new Uint8ClampedArray(4))).toThrow(/224×224/);
  });
});
