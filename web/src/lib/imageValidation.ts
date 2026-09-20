import type { InspectedImage } from "../types";

export const MAX_FILE_BYTES = 5 * 1024 * 1024;
export const MAX_PIXELS = 16_000_000;
export const MIN_DIMENSION = 224;
export const MAX_ASPECT_DIFFERENCE = 0.05;

export type ImageValidationCode =
  | "UNSUPPORTED_FORMAT"
  | "FILE_TOO_LARGE"
  | "ANIMATED_IMAGE"
  | "IMAGE_DECODE_FAILED"
  | "IMAGE_TOO_SMALL"
  | "IMAGE_TOO_LARGE"
  | "IDENTICAL_IMAGES"
  | "ASPECT_RATIO_MISMATCH";

export class ImageValidationError extends Error {
  readonly code: ImageValidationCode;

  constructor(code: ImageValidationCode, message: string) {
    super(message);
    this.name = "ImageValidationError";
    this.code = code;
  }
}

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

function hasBytes(bytes: Uint8Array, offset: number, expected: readonly number[]): boolean {
  return expected.every((value, index) => bytes[offset + index] === value);
}

function hasAscii(bytes: Uint8Array, value: string): boolean {
  const needle = new TextEncoder().encode(value);
  outer: for (let start = 0; start <= bytes.length - needle.length; start += 1) {
    for (let index = 0; index < needle.length; index += 1) {
      if (bytes[start + index] !== needle[index]) continue outer;
    }
    return true;
  }
  return false;
}

export function detectImageFormat(
  bytes: Uint8Array,
): "image/jpeg" | "image/png" | "image/webp" | null {
  if (bytes.length >= 3 && hasBytes(bytes, 0, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (bytes.length >= 8 && hasBytes(bytes, 0, PNG_SIGNATURE)) return "image/png";
  if (
    bytes.length >= 12 &&
    hasAscii(bytes.subarray(0, 4), "RIFF") &&
    hasAscii(bytes.subarray(8, 12), "WEBP")
  ) {
    return "image/webp";
  }
  return null;
}

export function isAnimatedImage(
  bytes: Uint8Array,
  mediaType: "image/jpeg" | "image/png" | "image/webp",
): boolean {
  if (mediaType === "image/png") return hasAscii(bytes, "acTL");
  if (mediaType === "image/webp") return hasAscii(bytes, "ANIM") || hasAscii(bytes, "ANMF");
  return false;
}

export function validateDimensions(width: number, height: number): void {
  if (width < MIN_DIMENSION || height < MIN_DIMENSION) {
    throw new ImageValidationError(
      "IMAGE_TOO_SMALL",
      `Each image must be at least ${MIN_DIMENSION} × ${MIN_DIMENSION} pixels.`,
    );
  }
  if (width * height > MAX_PIXELS) {
    throw new ImageValidationError(
      "IMAGE_TOO_LARGE",
      "Each image must contain no more than 16 megapixels.",
    );
  }
}

export function validatePair(before: InspectedImage, after: InspectedImage): void {
  if (before.sha256 === after.sha256) {
    throw new ImageValidationError(
      "IDENTICAL_IMAGES",
      "The before and after files are identical. Choose two different photographs.",
    );
  }

  const relativeDifference =
    Math.abs(before.aspectRatio - after.aspectRatio) /
    Math.max(before.aspectRatio, after.aspectRatio);
  if (relativeDifference > MAX_ASPECT_DIFFERENCE) {
    throw new ImageValidationError(
      "ASPECT_RATIO_MISMATCH",
      "The image shapes differ by more than 5%. Retake them from a comparable viewpoint.",
    );
  }
}

async function sha256(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

async function decodeDimensions(file: File): Promise<{ width: number; height: number }> {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const result = { width: bitmap.width, height: bitmap.height };
    bitmap.close();
    return result;
  } catch {
    throw new ImageValidationError(
      "IMAGE_DECODE_FAILED",
      "This file could not be decoded as an image.",
    );
  }
}

export async function inspectImage(file: File): Promise<InspectedImage> {
  if (file.size > MAX_FILE_BYTES) {
    throw new ImageValidationError("FILE_TOO_LARGE", "Each image must be 5 MB or smaller.");
  }

  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const mediaType = detectImageFormat(bytes);
  if (!mediaType) {
    throw new ImageValidationError(
      "UNSUPPORTED_FORMAT",
      "Choose a JPEG, PNG, or WebP image.",
    );
  }
  if (isAnimatedImage(bytes, mediaType)) {
    throw new ImageValidationError(
      "ANIMATED_IMAGE",
      "Animated images are not supported. Export a single still frame instead.",
    );
  }

  const { width, height } = await decodeDimensions(file);
  validateDimensions(width, height);

  return {
    file,
    width,
    height,
    aspectRatio: width / height,
    sha256: await sha256(buffer),
    mediaType,
  };
}

export function getValidationMessage(error: unknown): string {
  if (error instanceof ImageValidationError) return error.message;
  return "We could not validate this image. Try a different file.";
}
