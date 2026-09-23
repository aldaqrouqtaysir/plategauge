import { describe, expect, it } from "vitest";
import { getModelCropFrame } from "./framing";

describe("model-visible frame geometry", () => {
  it.each([
    [224, 224, 256, 256, 16, 16],
    [640, 480, 341, 256, 58, 16],
    [480, 640, 256, 341, 16, 58],
    [515, 512, 258, 256, 17, 16],
    [512, 515, 256, 258, 16, 17],
    [513, 512, 256, 256, 16, 16],
  ])("maps %i×%i using the exact integer resized crop", (w, h, resizedW, resizedH, left, top) => {
    expect(getModelCropFrame(w, h)).toEqual({ left: left / resizedW * 100, top: top / resizedH * 100, width: 224 / resizedW * 100, height: 224 / resizedH * 100 });
  });
  it("does not round an odd resized dimension to a symmetric CSS inset", () => {
    const frame = getModelCropFrame(640, 480);
    expect(frame.left).not.toBe((100 - frame.width) / 2);
    expect(frame.left + frame.width).toBeLessThan(100);
  });
  it.each([[0, 480], [640, Number.NaN], [640.5, 480], [16_000, 16_000]])("rejects invalid/over-budget dimensions %s×%s", (w, h) => {
    expect(() => getModelCropFrame(w, h)).toThrow();
  });
});
