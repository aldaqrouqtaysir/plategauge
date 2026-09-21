import type { InspectedImage } from "../types";
import { calculatePreprocessGeometry, prepareImage, type PreprocessGeometry } from "./preprocess";
import { rgbaToNormalizedChw } from "./tensorPreprocess";

export interface GoldenBrowserResult {
  geometry: PreprocessGeometry;
  rgbaSha256: string;
  tensorSha256: string;
  rgbaBase64: string;
  tensorBase64: string;
}

function base64(bytes: Uint8Array): string {
  // Test-only diagnostics; keep argument counts bounded for every browser.
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 8192) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  }
  return btoa(binary);
}

async function digestHex(buffer: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(hash)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function evaluateGoldenFile(file: File): Promise<GoldenBrowserResult> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const width = bitmap.width;
  const height = bitmap.height;
  bitmap.close();
  const inspected: InspectedImage = {
    file,
    width,
    height,
    aspectRatio: width / height,
    sha256: "0".repeat(64),
    mediaType: "image/png",
  };
  const prepared = await prepareImage(inspected);
  const rgba = new Uint8ClampedArray(prepared.rgba);
  const tensor = rgbaToNormalizedChw(rgba);
  return {
    geometry: calculatePreprocessGeometry(width, height),
    rgbaSha256: await digestHex(rgba.slice().buffer),
    tensorSha256: await digestHex(tensor.slice().buffer),
    rgbaBase64: base64(new Uint8Array(rgba.buffer)),
    tensorBase64: base64(new Uint8Array(tensor.buffer)),
  };
}

declare global {
  interface Window {
    __plateGaugePreprocessGolden?: (file: File) => Promise<GoldenBrowserResult>;
  }
}

if (import.meta.env.MODE === "test") {
  Object.defineProperty(window, "__plateGaugePreprocessGolden", {
    value: evaluateGoldenFile,
    configurable: false,
    enumerable: false,
    writable: false,
  });
}
