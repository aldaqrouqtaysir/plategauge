import { afterEach, describe, expect, it, vi } from "vitest";
import type { InspectedImage } from "../types";
import { calculatePreprocessGeometry, prepareImage } from "./preprocess";

function inspectedImage(): InspectedImage {
  return {
    file: new File([new Uint8Array([1, 2, 3])], "plate.png", { type: "image/png" }),
    width: 640,
    height: 480,
    aspectRatio: 4 / 3,
    sha256: "a".repeat(64),
    mediaType: "image/png",
  };
}

function stubBitmap(): { bitmap: ImageBitmap; close: ReturnType<typeof vi.fn> } {
  const close = vi.fn();
  const bitmap = { width: 640, height: 480, close } as unknown as ImageBitmap;
  vi.stubGlobal("createImageBitmap", vi.fn(() => Promise.resolve(bitmap)));
  return { bitmap, close };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("calculatePreprocessGeometry", () => {
  it.each([
    { input: [640, 480] as const, output: [341, 256, 58, 16] as const },
    { input: [480, 640] as const, output: [256, 341, 16, 58] as const },
    { input: [300, 300] as const, output: [256, 256, 16, 16] as const },
  ])("uses rounded integer resize dimensions and integer center crops", ({ input, output }) => {
    const geometry = calculatePreprocessGeometry(input[0], input[1]);
    expect([
      geometry.resizedWidth,
      geometry.resizedHeight,
      geometry.cropLeft,
      geometry.cropTop,
    ]).toEqual(output);
  });

  it("matches Python's ties-to-even rounding at exact half pixels", () => {
    expect(calculatePreprocessGeometry(513, 512).resizedWidth).toBe(256);
    expect(calculatePreprocessGeometry(515, 512).resizedWidth).toBe(258);
  });

  it("rejects invalid source dimensions", () => {
    const invalidDimensions: ReadonlyArray<readonly [number, number]> = [
      [0, 300],
      [300, -1],
      [300.5, 300],
    ];
    for (const [width, height] of invalidDimensions) {
      expect(() => calculatePreprocessGeometry(width, height)).toThrow(/positive integers/);
    }
  });

  it("resizes, center-crops, copies pixels, and releases the bitmap", async () => {
    const { bitmap, close } = stubBitmap();
    const resizeDraw = vi.fn();
    const cropDraw = vi.fn();
    const resizeContext = {
      imageSmoothingEnabled: false,
      imageSmoothingQuality: "low",
      drawImage: resizeDraw,
    } as unknown as CanvasRenderingContext2D;
    const pixels = new Uint8ClampedArray([17, 34, 51, 255]);
    const cropContext = {
      drawImage: cropDraw,
      getImageData: vi.fn(() => ({ data: pixels }) as ImageData),
    } as unknown as CanvasRenderingContext2D;
    let contextCall = 0;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => {
      contextCall += 1;
      return contextCall === 1 ? resizeContext : cropContext;
    });

    const prepared = await prepareImage(inspectedImage());

    expect(prepared.width).toBe(224);
    expect(prepared.height).toBe(224);
    expect(new Uint8ClampedArray(prepared.rgba)).toEqual(pixels);
    expect(resizeContext.imageSmoothingEnabled).toBe(true);
    expect(resizeContext.imageSmoothingQuality).toBe("high");
    expect(resizeDraw).toHaveBeenCalledWith(bitmap, 0, 0, 341, 256);
    expect(cropDraw).toHaveBeenCalledWith(expect.any(HTMLCanvasElement), 58, 16, 224, 224, 0, 0, 224, 224);
    expect(close).toHaveBeenCalledOnce();
  });

  it("reports unavailable canvas processing and still releases the bitmap", async () => {
    const { close } = stubBitmap();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);

    await expect(prepareImage(inspectedImage())).rejects.toThrow(/Canvas processing is unavailable/);
    expect(close).toHaveBeenCalledOnce();
  });
});
