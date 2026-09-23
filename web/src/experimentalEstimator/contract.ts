/** Experimental engineering baseline, not a promoted or camera-validated model. */
export const EXPERIMENTAL_MODEL = Object.freeze({
  version: "v1.0.0-paired-baseline/experimental-camera-r1",
  path: "models/plategauge.onnx",
  sha256: "9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675",
  bytes: 10_355_122,
});

export interface ExperimentalEstimate {
  leftoverFraction: number;
  modelVersion: string;
  processingMs: number;
}

export function experimentalContextAllowed(development: boolean, hostname: string,
  context?: { candidate: boolean; protocol: string; secureContext: boolean }): boolean {
  const loopback = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(hostname);
  // Legacy two-argument callers retain only the original development restriction.
  if (!context) return development && loopback;
  if (context.secureContext !== true || !["http:", "https:"].includes(context.protocol)) return false;
  return (development && loopback) || (context.candidate === true
    && (loopback || (context.protocol === "https:" && hostname === "aldaqrouqtaysir.github.io")));
}

export function medianFromOutput(values: readonly number[]): number {
  if (values.length !== 3 || values.some((v) => !Number.isFinite(v) || v < 0 || v > 1)
    || values[0]! > values[1]! || values[1]! > values[2]!) {
    throw new Error("The model returned an invalid result. No estimate is available.");
  }
  return values[1]!;
}

export function isExperimentalEstimate(value: unknown): value is ExperimentalEstimate {
  if (!value || typeof value !== "object") return false;
  if (Object.keys(value).sort().join(",") !== "leftoverFraction,modelVersion,processingMs") return false;
  const result = value as Partial<ExperimentalEstimate>;
  return result.modelVersion === EXPERIMENTAL_MODEL.version
    && typeof result.leftoverFraction === "number" && Number.isFinite(result.leftoverFraction)
    && result.leftoverFraction >= 0 && result.leftoverFraction <= 1
    && typeof result.processingMs === "number" && Number.isFinite(result.processingMs) && result.processingMs >= 0;
}

export function validModelPixels(width: number, height: number, data: unknown): data is Uint8ClampedArray<ArrayBuffer> {
  if (width !== 224 || height !== 224 || !(data instanceof Uint8ClampedArray)
    || !(data.buffer instanceof ArrayBuffer) || data.length !== 224 * 224 * 4
    || data.byteOffset !== 0 || data.byteLength !== data.buffer.byteLength) return false;
  for (let i = 3; i < data.length; i += 4) if (data[i] !== 255) return false;
  return true;
}
