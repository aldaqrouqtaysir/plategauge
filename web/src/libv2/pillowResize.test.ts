// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import goldens from "./pillowResizeGoldens.json";
import { estimateResizeBudget, PILLOW_RESIZE_LIMITS, PillowResizeError, pillowCropGeometry, preparePillowCrop, resizeOpaqueRgbaBicubic } from "./pillowResize";
import type { OpaqueRgbaImage } from "./pillowResize";

function fixture(width: number, height: number, kind = "uniform"): OpaqueRgbaImage {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const offset = (y * width + x) * 4;
      if (kind === "pattern") {
        data[offset] = (x * 17 + y * 11) % 256;
        data[offset + 1] = (x + y) % 2 * 255;
        data[offset + 2] = (x * 7 + y * 13) % 31 < 15 ? 255 : 0;
      } else if (kind === "edges") {
        data[offset] = x < Math.floor(width / 2) ? 255 : 0;
        data[offset + 1] = y < Math.floor(height / 2) ? 255 : 0;
        data[offset + 2] = x === 0 || y === height - 1 ? 255 : 0;
      } else {
        data[offset] = 17; data[offset + 1] = 101; data[offset + 2] = 233;
      }
      data[offset + 3] = 255;
    }
  }
  return { width, height, data };
}

async function hash(data: Uint8ClampedArray): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data.slice().buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("synthetic-only Pillow 12.3.0 bicubic references", () => {
  it.each(goldens.fixtures)("matches every output byte: $id", async (reference) => {
    expect(goldens.syntheticOnly).toBe(true);
    expect(goldens.pillowVersion).toBe("12.3.0");
    const input = fixture(reference.width, reference.height, reference.kind);
    const before = await hash(input.data);
    const result = reference.mode === "crop"
      ? await preparePillowCrop(input)
      : await resizeOpaqueRgbaBicubic(input, reference.outputWidth, reference.outputHeight);
    expect([result.width, result.height]).toEqual([reference.outputWidth, reference.outputHeight]);
    expect(await hash(result.data)).toBe(reference.expectedRgbaSha256);
    expect(await hash(input.data)).toBe(before);
    expect(result.data.buffer).not.toBe(input.data.buffer);
  });
});

describe("preflight and pixel boundaries", () => {
  it.each([0, -1, 1.5, NaN, Infinity, 16_385])("rejects invalid dimension %s before allocation", (value) => {
    expect(() => estimateResizeBudget(value, 1, 1, 1)).toThrow(PillowResizeError);
    expect(() => estimateResizeBudget(1, 1, 1, value)).toThrow(PillowResizeError);
  });
  it("rejects excess pixels and disproportionate intermediate allocations analytically", () => {
    expect(() => estimateResizeBudget(4001, 4000, 224, 224)).toThrow(/Pixel count/);
    expect(() => estimateResizeBudget(100, 10000, 16000, 1)).toThrow(/workspace/);
    expect(() => estimateResizeBudget(4000, 4000, 2000, 2000)).toThrow(/processing-work/);
  });
  it("uses Pillow's strict tall-image vertical-first threshold in its work budget", () => {
    expect(estimateResizeBudget(5, 500, 7, 127).passOrder).toBe("horizontal-vertical");
    expect(estimateResizeBudget(5, 501, 7, 127).passOrder).toBe("vertical-horizontal");
    expect(estimateResizeBudget(5, 1023, 7, 1024).passOrder).toBe("horizontal-vertical");
    expect(estimateResizeBudget(1, 16384, 16384, 1).workspaceBytes).toBeLessThan(2_000_000);
  });
  it("reports bounded finite work and memory estimates", () => {
    const budget = estimateResizeBudget(4000, 3000, 341, 256);
    expect(budget.inputPixels).toBe(12_000_000);
    expect(budget.outputPixels).toBe(341 * 256);
    expect(budget.workspaceBytes).toBeLessThan(PILLOW_RESIZE_LIMITS.maximumWorkspaceBytes);
    expect(budget.multiplyAdds).toBeLessThan(PILLOW_RESIZE_LIMITS.maximumMultiplyAdds);
    expect(Number.isSafeInteger(budget.multiplyAdds)).toBe(true);
  });
  it("rejects incomplete, wrong-type, and shared pixel arrays", async () => {
    await expect(resizeOpaqueRgbaBicubic({ width: 2, height: 2, data: new Uint8ClampedArray(4) }, 1, 1)).rejects.toThrow(/RGBA byte/);
    await expect(resizeOpaqueRgbaBicubic({ width: 1, height: 1, data: new Float32Array(4) as unknown as Uint8ClampedArray }, 1, 1)).rejects.toThrow(/RGBA byte/);
    if (typeof SharedArrayBuffer !== "undefined") {
      await expect(resizeOpaqueRgbaBicubic({ width: 1, height: 1, data: new Uint8ClampedArray(new SharedArrayBuffer(4)) }, 1, 1)).rejects.toThrow(/non-shared/);
    }
  });
  it.each([0, 1, 128, 254])("rejects alpha %i without changing the caller's pixels", async (alpha) => {
    const input = fixture(3, 3); input.data[3] = alpha;
    const before = await hash(input.data);
    await expect(resizeOpaqueRgbaBicubic(input, 5, 5)).rejects.toMatchObject({ code: "unsupported_alpha" });
    expect(await hash(input.data)).toBe(before);
  });
  it("matches the frozen Python ties-to-even geometry", () => {
    expect(pillowCropGeometry(513, 512)).toEqual({ resizedWidth: 256, resizedHeight: 256, cropLeft: 16, cropTop: 16 });
    expect(pillowCropGeometry(515, 512).resizedWidth).toBe(258);
    expect(() => pillowCropGeometry(16384, 1)).toThrow(PillowResizeError);
  });
  it("does not access image decoders, Canvas, models, network, or browser storage", async () => {
    const forbidden = vi.fn(() => { throw new Error("Forbidden browser API"); });
    vi.stubGlobal("fetch", forbidden);
    vi.stubGlobal("createImageBitmap", forbidden);
    vi.stubGlobal("Worker", forbidden);
    const result = await preparePillowCrop(fixture(256, 256, "pattern"));
    expect(result.data.length).toBe(224 * 224 * 4);
    expect(forbidden).not.toHaveBeenCalled();
  });
});

describe("cancellation and ownership", () => {
  it("rejects a pre-aborted operation", async () => {
    const controller = new AbortController(); controller.abort();
    await expect(preparePillowCrop(fixture(256, 256), { signal: controller.signal })).rejects.toMatchObject({ name: "AbortError" });
  });
  it("yields so a pending operation can be cancelled without changing input", async () => {
    vi.useFakeTimers();
    const input = fixture(512, 512); const before = await hash(input.data);
    const controller = new AbortController();
    const processing = resizeOpaqueRgbaBicubic(input, 224, 224, { signal: controller.signal });
    const rejection = expect(processing).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();
    await vi.runAllTimersAsync();
    await rejection;
    expect(await hash(input.data)).toBe(before);
  });
  it("uses a private snapshot when input is changed during an async yield", async () => {
    vi.useFakeTimers();
    const input = fixture(512, 512);
    const processing = resizeOpaqueRgbaBicubic(input, 16, 16);
    input.data.fill(0);
    await vi.runAllTimersAsync();
    const result = await processing;
    expect(await hash(result.data)).toBe(await hash(fixture(16, 16).data));
    expect(input.data.every((value) => value === 0)).toBe(true);
  });
  it("snapshots source dimensions rather than rereading mutable caller metadata after a yield", async () => {
    vi.useFakeTimers();
    const original = fixture(512, 512);
    const input = { ...original };
    const processing = resizeOpaqueRgbaBicubic(input, 16, 16);
    input.width = 1; input.height = 1; input.data = new Uint8ClampedArray(4);
    await vi.runAllTimersAsync();
    const result = await processing;
    expect(await hash(result.data)).toBe(await hash(fixture(16, 16).data));
    expect(original.data[0]).toBe(17);
  });
});
