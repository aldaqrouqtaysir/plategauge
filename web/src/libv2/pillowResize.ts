/**
 * Isolated opaque-RGB resampling compatible with Pillow 12.3.0's 8-bit BICUBIC path.
 * Coefficient/filter behavior derived from Pillow's MIT-CMU-licensed Resample.c.
 * Copyright © 1997-2011 Secret Labs AB; © 1995-2011 Fredrik Lundh and contributors;
 * © 2010 Jeffrey 'Alex' Clark and contributors. See PILLOW_RESAMPLING_NOTICE.md.
 *
 * This accepts decoded pixels, not files: EXIF, ICC conversion, alpha compositing,
 * image decoding, letterboxing, and model inference are deliberately out of scope.
 */

export interface OpaqueRgbaImage {
  readonly width: number;
  readonly height: number;
  readonly data: Uint8ClampedArray;
}

export interface ResizeOptions {
  readonly signal?: AbortSignal;
}

export const PILLOW_RESIZE_LIMITS = Object.freeze({
  maximumDimension: 16_384,
  maximumPixels: 16_000_000,
  maximumWorkspaceBytes: 128 * 1024 * 1024,
  maximumMultiplyAdds: 250_000_000,
  yieldAfterMultiplyAdds: 262_144,
  yieldAfterAlphaPixels: 262_144,
});

export type PillowResizeErrorCode =
  | "invalid_dimensions"
  | "pixel_limit"
  | "workspace_limit"
  | "work_limit"
  | "invalid_buffer"
  | "unsupported_alpha"
  | "invalid_coefficients";

export class PillowResizeError extends Error {
  constructor(readonly code: PillowResizeErrorCode, message: string) {
    super(message);
    this.name = "PillowResizeError";
  }
}

interface AxisPlan {
  readonly inputSize: number;
  readonly outputSize: number;
  readonly kernelSize: number;
  readonly scale: number;
  readonly filterScale: number;
  readonly support: number;
  readonly tapCount: number;
  readonly workspaceBytes: number;
}

interface Coefficients {
  readonly plan: AxisPlan;
  readonly starts: Int32Array;
  readonly counts: Int32Array;
  readonly weights: Int32Array;
}

export interface ResizeBudget {
  readonly inputPixels: number;
  readonly outputPixels: number;
  /** Private input snapshot + allocated passes + coefficient storage/scratch. */
  readonly workspaceBytes: number;
  /** RGB scalar multiply-adds; validation/copy/yield work is additional. */
  readonly multiplyAdds: number;
  readonly passOrder: "horizontal-vertical" | "vertical-horizontal";
}

const COEFFICIENT_SCALE = 2 ** 22;
const ROUNDING_OFFSET = COEFFICIENT_SCALE / 2;

function dimensions(width: number, height: number): number {
  if (![width, height].every((value) => Number.isInteger(value) && value > 0 && value <= PILLOW_RESIZE_LIMITS.maximumDimension)) {
    throw new PillowResizeError("invalid_dimensions", "Dimensions must be positive integers no greater than 16384.");
  }
  const pixels = width * height;
  if (pixels > PILLOW_RESIZE_LIMITS.maximumPixels) {
    throw new PillowResizeError("pixel_limit", "Pixel count exceeds the 16-million-pixel processing limit.");
  }
  return pixels;
}

function bounds(plan: AxisPlan, output: number): readonly [number, number] {
  const center = (output + 0.5) * plan.scale;
  // C casts truncate toward zero, including negative support at the first pixel.
  const start = Math.max(0, Math.trunc(center - plan.support + 0.5));
  const end = Math.min(plan.inputSize, Math.trunc(center + plan.support + 0.5));
  return [start, end - start];
}

function axisPlan(inputSize: number, outputSize: number): AxisPlan | null {
  if (inputSize === outputSize) return null;
  const scale = inputSize / outputSize;
  const filterScale = Math.max(1, scale);
  const support = 2 * filterScale;
  const kernelSize = Math.ceil(support) * 2 + 1;
  const base: AxisPlan = { inputSize, outputSize, scale, filterScale, support, kernelSize, tapCount: 0, workspaceBytes: 0 };
  let tapCount = 0;
  for (let output = 0; output < outputSize; output++) tapCount += bounds(base, output)[1];
  return {
    ...base,
    tapCount,
    workspaceBytes: outputSize * kernelSize * 4 + outputSize * 8 + kernelSize * 8,
  };
}

/** Preflight can be tested without allocating an image. Limits are not caller-overridable. */
export function estimateResizeBudget(inputWidth: number, inputHeight: number, outputWidth: number, outputHeight: number): ResizeBudget {
  const inputPixels = dimensions(inputWidth, inputHeight);
  const outputPixels = dimensions(outputWidth, outputHeight);
  const horizontal = axisPlan(inputWidth, outputWidth);
  const vertical = axisPlan(inputHeight, outputHeight);
  // Pillow Image.resize (12.3.0) performs the vertical pass first for this
  // highly tall/narrow downscale case. Per-axis byte clipping makes order matter.
  const verticalFirst = inputHeight > inputWidth * 100 && outputHeight < inputHeight;
  const workspaceBytes = inputPixels * 4
    + (horizontal ? outputWidth * (verticalFirst ? outputHeight : inputHeight) * 4 + horizontal.workspaceBytes : 0)
    + (vertical ? (verticalFirst ? inputWidth * outputHeight : outputPixels) * 4 + vertical.workspaceBytes : 0);
  const multiplyAdds = 3 * ((horizontal?.tapCount ?? 0) * (verticalFirst ? outputHeight : inputHeight)
    + (vertical?.tapCount ?? 0) * (verticalFirst ? inputWidth : outputWidth));
  if (!Number.isSafeInteger(workspaceBytes) || workspaceBytes > PILLOW_RESIZE_LIMITS.maximumWorkspaceBytes) {
    throw new PillowResizeError("workspace_limit", "Resize workspace exceeds the 128 MiB allocation limit.");
  }
  if (!Number.isSafeInteger(multiplyAdds) || multiplyAdds > PILLOW_RESIZE_LIMITS.maximumMultiplyAdds) {
    throw new PillowResizeError("work_limit", "Resize exceeds the bounded processing-work limit.");
  }
  return { inputPixels, outputPixels, workspaceBytes, multiplyAdds, passOrder: verticalFirst ? "vertical-horizontal" : "horizontal-vertical" };
}

function cubic(distance: number): number {
  const x = Math.abs(distance);
  if (x < 1) return (1.5 * x - 2.5) * x * x + 1;
  if (x < 2) return (((x - 5) * x + 8) * x - 4) * -0.5;
  return 0;
}

function coefficients(plan: AxisPlan): Coefficients {
  const starts = new Int32Array(plan.outputSize);
  const counts = new Int32Array(plan.outputSize);
  const weights = new Int32Array(plan.outputSize * plan.kernelSize);
  const unnormalized = new Float64Array(plan.kernelSize);
  const inverseFilterScale = 1 / plan.filterScale;
  for (let output = 0; output < plan.outputSize; output++) {
    const [start, count] = bounds(plan, output);
    const center = (output + 0.5) * plan.scale;
    let sum = 0;
    for (let tap = 0; tap < count; tap++) {
      const weight = cubic((tap + start - center + 0.5) * inverseFilterScale);
      unnormalized[tap] = weight;
      sum += weight;
    }
    if (!Number.isFinite(sum) || sum === 0 || count < 1) {
      throw new PillowResizeError("invalid_coefficients", "Resampling produced invalid coefficients.");
    }
    for (let tap = 0; tap < count; tap++) {
      const normalized = unnormalized[tap]! / sum;
      const quantized = Math.trunc(normalized * COEFFICIENT_SCALE + (normalized < 0 ? -0.5 : 0.5));
      if (!Number.isSafeInteger(quantized) || Math.abs(quantized) > 2 ** 31 - 1) {
        throw new PillowResizeError("invalid_coefficients", "Resampling coefficient is not a finite bounded integer.");
      }
      weights[output * plan.kernelSize + tap] = quantized;
    }
    starts[output] = start;
    counts[output] = count;
  }
  return { plan, starts, counts, weights };
}

function abortIfRequested(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("Image processing was cancelled.", "AbortError");
}

async function yieldProcessing(signal?: AbortSignal): Promise<void> {
  abortIfRequested(signal);
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
  abortIfRequested(signal);
}

function roundedByte(accumulator: number): number {
  // Division avoids JavaScript's signed 32-bit bitwise coercion. Integer sums
  // remain exactly representable here; clipping occurs after each separate axis.
  return Math.max(0, Math.min(255, Math.floor(accumulator / COEFFICIENT_SCALE)));
}

async function filterPass(source: OpaqueRgbaImage, destination: OpaqueRgbaImage, table: Coefficients, horizontal: boolean, signal?: AbortSignal): Promise<void> {
  let workSinceYield = 0;
  for (let y = 0; y < destination.height; y++) {
    for (let x = 0; x < destination.width; x++) {
      const axisPosition = horizontal ? x : y;
      const start = table.starts[axisPosition]!;
      const count = table.counts[axisPosition]!;
      const weightOffset = axisPosition * table.plan.kernelSize;
      let red = ROUNDING_OFFSET;
      let green = ROUNDING_OFFSET;
      let blue = ROUNDING_OFFSET;
      for (let tap = 0; tap < count; tap++) {
        const offset = (horizontal ? y * source.width + start + tap : (start + tap) * source.width + x) * 4;
        const weight = table.weights[weightOffset + tap]!;
        red += source.data[offset]! * weight;
        green += source.data[offset + 1]! * weight;
        blue += source.data[offset + 2]! * weight;
      }
      const outputOffset = (y * destination.width + x) * 4;
      destination.data[outputOffset] = roundedByte(red);
      destination.data[outputOffset + 1] = roundedByte(green);
      destination.data[outputOffset + 2] = roundedByte(blue);
      destination.data[outputOffset + 3] = 255;
      workSinceYield += count * 3;
      if (workSinceYield >= PILLOW_RESIZE_LIMITS.yieldAfterMultiplyAdds) {
        await yieldProcessing(signal);
        workSinceYield = 0;
      }
    }
  }
  abortIfRequested(signal);
}

/**
 * Resizes an opaque, decoded RGBA image using the Pillow RGB bicubic arithmetic.
 * Owns a snapshot: caller mutation during an async yield cannot change results.
 * Input is never cleared; private intermediate pixels are cleared on every exit.
 * No browser Canvas, Worker, file, network, storage, or model API is accessed.
 */
export async function resizeOpaqueRgbaBicubic(image: OpaqueRgbaImage, outputWidth: number, outputHeight: number, options: ResizeOptions = {}): Promise<OpaqueRgbaImage> {
  const { width: inputWidth, height: inputHeight, data: inputData } = image;
  const signal = options.signal;
  abortIfRequested(signal);
  const budget = estimateResizeBudget(inputWidth, inputHeight, outputWidth, outputHeight);
  if (!(inputData instanceof Uint8ClampedArray) || inputData.length !== budget.inputPixels * 4
    || !(inputData.buffer instanceof ArrayBuffer)) {
    throw new PillowResizeError("invalid_buffer", "Expected a non-shared RGBA byte array matching the source dimensions.");
  }
  const owned: Uint8ClampedArray[] = [];
  let result: OpaqueRgbaImage | undefined;
  try {
    let current: OpaqueRgbaImage = { width: inputWidth, height: inputHeight, data: new Uint8ClampedArray(inputData) };
    owned.push(current.data);
    for (let pixel = 0; pixel < budget.inputPixels; pixel++) {
      if (current.data[pixel * 4 + 3] !== 255) {
        throw new PillowResizeError("unsupported_alpha", "Only fully opaque RGB pixels are supported; transparency must not be silently composited.");
      }
      if ((pixel + 1) % PILLOW_RESIZE_LIMITS.yieldAfterAlphaPixels === 0) await yieldProcessing(signal);
    }
    const horizontalFirst = budget.passOrder === "horizontal-vertical";
    for (const horizontal of [horizontalFirst, !horizontalFirst]) {
      const plan = horizontal ? axisPlan(inputWidth, outputWidth) : axisPlan(inputHeight, outputHeight);
      if (!plan) continue;
      const width = horizontal ? outputWidth : current.width;
      const height = horizontal ? current.height : outputHeight;
      const next = { width, height, data: new Uint8ClampedArray(width * height * 4) };
      owned.push(next.data);
      await filterPass(current, next, coefficients(plan), horizontal, signal);
      current = next;
    }
    abortIfRequested(signal);
    result = current;
    return result;
  } finally {
    for (const pixels of owned) if (pixels !== result?.data) pixels.fill(0);
  }
}

function roundHalfToEven(value: number): number {
  const lower = Math.floor(value);
  const fraction = value - lower;
  if (fraction < 0.5) return lower;
  if (fraction > 0.5) return lower + 1;
  return lower % 2 === 0 ? lower : lower + 1;
}

/** Model-card geometry only: short edge 256, then an integer-centered 224 crop. */
export function pillowCropGeometry(width: number, height: number): { resizedWidth: number; resizedHeight: number; cropLeft: number; cropTop: number } {
  dimensions(width, height);
  const scale = 256 / Math.min(width, height);
  const resizedWidth = Math.max(256, roundHalfToEven(width * scale));
  const resizedHeight = Math.max(256, roundHalfToEven(height * scale));
  estimateResizeBudget(width, height, resizedWidth, resizedHeight);
  return { resizedWidth, resizedHeight, cropLeft: Math.floor((resizedWidth - 224) / 2), cropTop: Math.floor((resizedHeight - 224) / 2) };
}

/** Crop candidate for synthetic-only prototype capture; frozen v1 remains unchanged. */
export async function preparePillowCrop(image: OpaqueRgbaImage, options: ResizeOptions = {}): Promise<OpaqueRgbaImage> {
  const signal = options.signal;
  abortIfRequested(signal);
  const geometry = pillowCropGeometry(image.width, image.height);
  const resized = await resizeOpaqueRgbaBicubic(image, geometry.resizedWidth, geometry.resizedHeight, { signal });
  let cropped: Uint8ClampedArray | undefined;
  let completed = false;
  try {
    abortIfRequested(signal);
    cropped = new Uint8ClampedArray(224 * 224 * 4);
    for (let y = 0; y < 224; y++) {
      const sourceOffset = ((y + geometry.cropTop) * resized.width + geometry.cropLeft) * 4;
      cropped.set(resized.data.subarray(sourceOffset, sourceOffset + 224 * 4), y * 224 * 4);
    }
    abortIfRequested(signal);
    completed = true;
    return { width: 224, height: 224, data: cropped };
  } finally {
    if (!completed) cropped?.fill(0);
    resized.data.fill(0);
  }
}
