/// <reference lib="webworker" />

import * as ort from "onnxruntime-web/wasm";
import { parseReleaseManifest, type ReleaseManifest } from "../lib/releaseManifest";
import { createDeterministicTestPrediction } from "../lib/testModel";
import { rgbaToNormalizedChw } from "../lib/tensorPreprocess";
import type { ModelErrorCode, PreparedImage, RawQuantiles } from "../types";
import type { ModelWorkerRequest, ModelWorkerResponse } from "./protocol";

declare const self: DedicatedWorkerGlobalScope;

const TEST_MODEL_ENABLED =
  import.meta.env.MODE !== "production" &&
  import.meta.env.VITE_PLATEGAUGE_TEST_MODEL === "enabled";

const baseUrl = new URL(import.meta.env.BASE_URL, self.location.origin);
const releaseManifestUrl = new URL("models/release.json", baseUrl);

let session: ort.InferenceSession | null = null;
let manifest: ReleaseManifest | null = null;
let initialization: Promise<void> | null = null;

class WorkerModelError extends Error {
  readonly code: ModelErrorCode;

  constructor(code: ModelErrorCode, message: string) {
    super(message);
    this.code = code;
    this.name = "WorkerModelError";
  }
}

function post(response: ModelWorkerResponse): void {
  self.postMessage(response);
}

async function digestHex(buffer: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(hash)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function loadManifest(): Promise<ReleaseManifest> {
  let response: Response;
  try {
    response = await fetch(releaseManifestUrl, {
      cache: "no-cache",
      credentials: "same-origin",
    });
  } catch {
    throw new WorkerModelError(
      "MODEL_MANIFEST_MISSING",
      "The frozen model release manifest could not be loaded.",
    );
  }
  if (!response.ok) {
    throw new WorkerModelError(
      "MODEL_MANIFEST_MISSING",
      "The frozen model release is not installed in this build.",
    );
  }
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    throw new WorkerModelError(
      "MODEL_MANIFEST_INVALID",
      "The model release manifest is not valid JSON.",
    );
  }
  const parsed = parseReleaseManifest(raw);
  if (!parsed) {
    throw new WorkerModelError(
      "MODEL_MANIFEST_INVALID",
      "The model release manifest failed schema validation.",
    );
  }
  return parsed;
}

async function loadModel(release: ReleaseManifest): Promise<ort.InferenceSession> {
  const modelUrl = new URL(release.modelPath, baseUrl);
  if (
    modelUrl.origin !== baseUrl.origin ||
    !modelUrl.pathname.startsWith(baseUrl.pathname)
  ) {
    throw new WorkerModelError(
      "MODEL_MANIFEST_INVALID",
      "The model artifact must be served from this application.",
    );
  }

  let response: Response;
  try {
    response = await fetch(modelUrl, { cache: "force-cache", credentials: "same-origin" });
  } catch {
    throw new WorkerModelError(
      "MODEL_ARTIFACT_MISSING",
      "The frozen ONNX model could not be loaded.",
    );
  }
  if (!response.ok) {
    throw new WorkerModelError(
      "MODEL_ARTIFACT_MISSING",
      "The frozen ONNX model is not installed in this build.",
    );
  }
  const model = await response.arrayBuffer();
  if ((await digestHex(model)) !== release.modelSha256) {
    throw new WorkerModelError(
      "MODEL_CHECKSUM_MISMATCH",
      "The model checksum does not match the frozen release manifest.",
    );
  }

  ort.env.wasm.numThreads = 1;
  ort.env.wasm.proxy = false;
  ort.env.wasm.wasmPaths = new URL("ort/", baseUrl).toString();
  try {
    return await ort.InferenceSession.create(model, {
      executionProviders: ["wasm"],
      graphOptimizationLevel: "all",
    });
  } catch {
    throw new WorkerModelError(
      "MODEL_RUNTIME_ERROR",
      "The frozen model could not be initialized by ONNX Runtime.",
    );
  }
}

async function initialize(): Promise<void> {
  if (TEST_MODEL_ENABLED || session) return;
  if (!initialization) {
    initialization = (async () => {
      manifest = await loadManifest();
      session = await loadModel(manifest);
    })();
  }
  await initialization;
}

function toTensor(image: PreparedImage): ort.Tensor {
  if (image.width !== 224 || image.height !== 224) {
    throw new WorkerModelError("MODEL_RUNTIME_ERROR", "Unexpected image tensor dimensions.");
  }
  const rgba = new Uint8ClampedArray(image.rgba);
  if (rgba.length !== 224 * 224 * 4) {
    throw new WorkerModelError("MODEL_RUNTIME_ERROR", "Unexpected image buffer length.");
  }
  const values = rgbaToNormalizedChw(rgba);
  return new ort.Tensor("float32", values, [1, 3, 224, 224]);
}

function validateQuantiles(values: readonly number[]): [number, number, number] {
  if (values.length < 3 || values.slice(0, 3).some((value) => !Number.isFinite(value))) {
    throw new WorkerModelError("MODEL_OUTPUT_INVALID", "The model returned invalid quantiles.");
  }
  const [rawLower = Number.NaN, rawMedian = Number.NaN, rawUpper = Number.NaN] = values;
  const tolerance = 1e-4;
  if (
    rawLower < -tolerance ||
    rawUpper > 1 + tolerance ||
    rawLower > rawMedian + tolerance ||
    rawMedian > rawUpper + tolerance
  ) {
    throw new WorkerModelError(
      "MODEL_OUTPUT_INVALID",
      "The model output violated the frozen quantile contract.",
    );
  }
  const clamp = (value: number): number => Math.max(0, Math.min(1, value));
  return [clamp(rawLower), clamp(rawMedian), clamp(rawUpper)];
}

async function infer(before: PreparedImage, after: PreparedImage): Promise<RawQuantiles> {
  const startedAt = performance.now();
  if (TEST_MODEL_ENABLED) {
    return createDeterministicTestPrediction(before, after);
  }

  await initialize();
  if (!session || !manifest) {
    throw new WorkerModelError("MODEL_RUNTIME_ERROR", "The model session is unavailable.");
  }
  const beforeTensor = toTensor(before);
  const afterTensor = toTensor(after);
  try {
    const outputs = await session.run({
      [manifest.beforeInputName]: beforeTensor,
      [manifest.afterInputName]: afterTensor,
    });
    try {
      const output = outputs[manifest.outputName];
      if (!output) {
        throw new WorkerModelError("MODEL_OUTPUT_INVALID", "The expected model output is missing.");
      }
      if (!(output.data instanceof Float32Array)) {
        throw new WorkerModelError(
          "MODEL_OUTPUT_INVALID",
          "The expected floating-point model output is missing.",
        );
      }
      const rawValues: number[] = [...output.data];
      const [rawLower, median, rawUpper] = validateQuantiles(rawValues);
      const lower = Math.max(0, rawLower - manifest.calibration.lowerExpansion);
      const upper = Math.min(1, rawUpper + manifest.calibration.upperExpansion);
      return {
        q05: lower,
        q50: median,
        q95: upper,
        modelVersion: manifest.modelVersion,
        intervalGatePassed: manifest.calibration.intervalGatePassed,
        abstentionWidth: manifest.calibration.abstentionWidth,
        isTestAdapter: false,
        processingMs: performance.now() - startedAt,
      };
    } finally {
      for (const value of Object.values(outputs)) value.dispose();
    }
  } finally {
    beforeTensor.dispose();
    afterTensor.dispose();
  }
}

function asWorkerError(error: unknown): WorkerModelError {
  if (error instanceof WorkerModelError) return error;
  return new WorkerModelError(
    "MODEL_RUNTIME_ERROR",
    "The browser model encountered an unexpected error.",
  );
}

self.addEventListener("message", (event: MessageEvent<ModelWorkerRequest>) => {
  const request = event.data;
  void (async () => {
    try {
      if (request.type === "init") {
        await initialize();
        post({
          type: "ready",
          requestId: request.requestId,
          modelVersion: TEST_MODEL_ENABLED
            ? "test-adapter/not-a-model"
            : (manifest?.modelVersion ?? "unknown"),
          isTestAdapter: TEST_MODEL_ENABLED,
        });
      } else if (request.type === "infer") {
        post({
          type: "result",
          requestId: request.requestId,
          result: await infer(request.before, request.after),
        });
      } else {
        if (session) await session.release();
        session = null;
        manifest = null;
        post({ type: "disposed", requestId: request.requestId });
        self.close();
      }
    } catch (error) {
      const workerError = asWorkerError(error);
      post({
        type: "error",
        requestId: request.requestId,
        code: workerError.code,
        message: workerError.message,
      });
    }
  })();
});
