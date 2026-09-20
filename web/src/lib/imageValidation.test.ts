import { describe, expect, it, vi } from "vitest";
import type { InspectedImage } from "../types";
import {
  detectImageFormat,
  getValidationMessage,
  ImageValidationError,
  inspectImage,
  isAnimatedImage,
  MAX_FILE_BYTES,
  validateDimensions,
  validatePair,
} from "./imageValidation";

const ascii = (value: string) => new TextEncoder().encode(value);

function inspected(overrides: Partial<InspectedImage> = {}): InspectedImage {
  return {
    file: new File(["x"], "image.png", { type: "image/png" }),
    width: 400,
    height: 300,
    aspectRatio: 4 / 3,
    sha256: "a".repeat(64),
    mediaType: "image/png",
    ...overrides,
  };
}

describe("image header validation", () => {
  it("detects supported image signatures rather than trusting the extension", () => {
    expect(detectImageFormat(new Uint8Array([0xff, 0xd8, 0xff]))).toBe("image/jpeg");
    expect(
      detectImageFormat(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10])),
    ).toBe("image/png");
    expect(detectImageFormat(ascii("RIFF1234WEBP"))).toBe("image/webp");
    expect(detectImageFormat(ascii("not an image"))).toBeNull();
  });

  it("rejects animated PNG and WebP markers", () => {
    expect(isAnimatedImage(ascii("headeracTLbody"), "image/png")).toBe(true);
    expect(isAnimatedImage(ascii("headerANMFbody"), "image/webp")).toBe(true);
    expect(isAnimatedImage(ascii("headerANIMbody"), "image/webp")).toBe(true);
    expect(isAnimatedImage(ascii("plain"), "image/jpeg")).toBe(false);
  });
});

describe("dimension and pair validation", () => {
  it("accepts dimensions inside the documented bounds", () => {
    expect(() => validateDimensions(224, 224)).not.toThrow();
    expect(() => validateDimensions(4_000, 4_000)).not.toThrow();
  });

  it("rejects undersized and oversized images", () => {
    expect(() => validateDimensions(223, 500)).toThrowError(ImageValidationError);
    expect(() => validateDimensions(4_001, 4_000)).toThrow(/16 megapixels/);
  });

  it("rejects identical files and mismatched aspect ratios", () => {
    expect(() => validatePair(inspected(), inspected())).toThrow(/identical/);
    expect(() =>
      validatePair(inspected(), inspected({ sha256: "b".repeat(64), aspectRatio: 1 })),
    ).toThrow(/more than 5%/);
  });

  it("accepts a non-identical pair within the aspect tolerance", () => {
    expect(() =>
      validatePair(inspected(), inspected({ sha256: "b".repeat(64), aspectRatio: 1.29 })),
    ).not.toThrow();
  });

  it("uses a safe generic message for unknown errors", () => {
    expect(getValidationMessage(new Error("private detail"))).not.toContain("private detail");
    expect(
      getValidationMessage(new ImageValidationError("FILE_TOO_LARGE", "Friendly message")),
    ).toBe("Friendly message");
  });

  it("documents the five-megabyte byte limit", () => {
    expect(MAX_FILE_BYTES).toBe(5 * 1024 * 1024);
    vi.restoreAllMocks();
  });
});

describe("inspectImage", () => {
  const pngBytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10, 0, 0, 0, 0]);

  function fakeFile(bytes: Uint8Array, size = bytes.byteLength): File {
    return {
      name: "test.png",
      size,
      type: "image/png",
      arrayBuffer: vi.fn().mockResolvedValue(bytes.buffer),
    } as unknown as File;
  }

  it("inspects a valid decoded still image and hashes its bytes", async () => {
    const close = vi.fn();
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn().mockResolvedValue({ width: 640, height: 480, close }),
    );
    vi.stubGlobal("crypto", {
      subtle: { digest: vi.fn().mockResolvedValue(new Uint8Array(32).fill(10).buffer) },
    });
    const image = await inspectImage(fakeFile(pngBytes));
    expect(image).toMatchObject({
      width: 640,
      height: 480,
      aspectRatio: 4 / 3,
      mediaType: "image/png",
      sha256: "0a".repeat(32),
    });
    expect(close).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it("rejects files over five megabytes before reading them", async () => {
    await expect(inspectImage(fakeFile(pngBytes, MAX_FILE_BYTES + 1))).rejects.toMatchObject({
      code: "FILE_TOO_LARGE",
    });
  });

  it("rejects unsupported bytes and animated images", async () => {
    await expect(inspectImage(fakeFile(ascii("plain text")))).rejects.toMatchObject({
      code: "UNSUPPORTED_FORMAT",
    });
    const animated = new Uint8Array([...pngBytes, ...ascii("acTL")]);
    await expect(inspectImage(fakeFile(animated))).rejects.toMatchObject({
      code: "ANIMATED_IMAGE",
    });
  });

  it("returns a safe decode failure", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("decoder detail")));
    await expect(inspectImage(fakeFile(pngBytes))).rejects.toMatchObject({
      code: "IMAGE_DECODE_FAILED",
    });
    vi.unstubAllGlobals();
  });
});
