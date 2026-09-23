/// <reference lib="webworker" />
import * as ort from "onnxruntime-web/wasm";
import { rgbaToNormalizedChw } from "../lib/tensorPreprocess";
import { EXPERIMENTAL_MODEL, experimentalContextAllowed, medianFromOutput, validModelPixels } from "./contract";
import type { OpaqueRgbaImage } from "../libv2/pillowResize";
import { readModelBytes } from "./modelBytes";

declare const self: DedicatedWorkerGlobalScope;
let started = false;

async function infer(request: { before: OpaqueRgbaImage; after: OpaqueRgbaImage }): Promise<void> {
  const startedAt = performance.now();
  const images = [request?.before, request?.after];
  const tensors: ort.Tensor[] = [];
  const values: Float32Array[] = [];
  let outputs: ort.InferenceSession.ReturnType | undefined;
  let session: ort.InferenceSession | undefined;
  let model: ArrayBuffer | undefined;
  try {
    if (!experimentalContextAllowed(import.meta.env.DEV, self.location.hostname, {
      candidate: import.meta.env.VITE_PLATEGAUGE_CAMERA_CANDIDATE === "1",
      protocol: self.location.protocol, secureContext: self.isSecureContext,
    })) throw new Error("context rejected");
    if (!request || Object.keys(request).sort().join(",") !== "after,before") throw new Error("invalid request");
    for (const image of images) {
      if (!image || !validModelPixels(image.width, image.height, image.data)) throw new Error("invalid input");
    }
    const base = new URL(import.meta.env.BASE_URL, self.location.origin);
    if (base.origin !== self.location.origin || base.username || base.password || base.search || base.hash) throw new Error("nonlocal asset base");
    const modelUrl = new URL(EXPERIMENTAL_MODEL.path, base);
    const response = await fetch(modelUrl, {
      method: "GET", mode: "same-origin", cache: "force-cache", credentials: "omit", redirect: "error",
    });
    model = await readModelBytes(response, modelUrl);
    const digest = await crypto.subtle.digest("SHA-256", model);
    const hex = [...new Uint8Array(digest)].map((v) => v.toString(16).padStart(2, "0")).join("");
    if (hex !== EXPERIMENTAL_MODEL.sha256) throw new Error("model checksum mismatch");
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.proxy = false;
    ort.env.wasm.wasmPaths = new URL("ort/", base).toString();
    session = await ort.InferenceSession.create(model, { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
    if (session.inputNames.join(",") !== "before,after" || session.outputNames.join(",") !== "quantiles") throw new Error("model contract mismatch");
    for (const image of images) {
      const normalized = rgbaToNormalizedChw(image.data);
      values.push(normalized);
      if (!normalized.every(Number.isFinite)) throw new Error("invalid tensor");
      tensors.push(new ort.Tensor("float32", normalized, [1, 3, 224, 224]));
    }
    outputs = await session.run({ before: tensors[0]!, after: tensors[1]! });
    const output = outputs.quantiles;
    if (!output || output.dims.join(",") !== "1,3" || !(output.data instanceof Float32Array)) throw new Error("invalid output shape");
    const leftoverFraction = medianFromOutput([...output.data]);
    self.postMessage({ leftoverFraction, modelVersion: EXPERIMENTAL_MODEL.version, processingMs: performance.now() - startedAt });
  } catch {
    // Sanitized status only: never log pixels, device details, or predictions.
    self.postMessage({ error: "estimation_unavailable" });
  } finally {
    // Independent best-effort cleanup: one runtime failure must not skip other wipes.
    if (outputs) for (const tensor of Object.values(outputs)) { try { tensor.dispose(); } catch { /* no private logging */ } }
    for (const tensor of tensors) { try { tensor.dispose(); } catch { /* no private logging */ } }
    for (const value of values) value.fill(0);
    for (const image of images) if (image?.data instanceof Uint8ClampedArray && image.data.buffer instanceof ArrayBuffer) image.data.fill(0);
    try { await session?.release(); } catch { /* no private logging */ }
    finally { if (model) new Uint8Array(model).fill(0); self.close(); }
  }
}

self.addEventListener("message", (event: MessageEvent<{ before: OpaqueRgbaImage; after: OpaqueRgbaImage }>) => {
  if (started) return;
  started = true;
  void infer(event.data);
});
