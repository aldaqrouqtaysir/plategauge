import type { CameraPhoto } from "../captureCamera/camera";
import type { OpaqueRgbaImage } from "../libv2/pillowResize";
import { experimentalContextAllowed, isExperimentalEstimate, validModelPixels, type ExperimentalEstimate } from "./contract";

const TIMEOUT_MS = 60_000;
const CANCELLED = "Estimate cancelled. No result was kept.";

/** One worker per explicit request: cancellation destroys the session and its transferred images. */
export async function estimatePair(before: CameraPhoto, after: CameraPhoto, signal: AbortSignal): Promise<ExperimentalEstimate> {
  if (!experimentalContextAllowed(import.meta.env.DEV, location.hostname, {
    candidate: import.meta.env.VITE_PLATEGAUGE_CAMERA_CANDIDATE === "1",
    protocol: location.protocol, secureContext: globalThis.isSecureContext,
  })) throw new Error("Estimation is available only in the approved secure candidate or local preview.");
  if (signal.aborted) throw new Error(CANCELLED);
  const beforeAspect = before.width / before.height;
  const afterAspect = after.width / after.height;
  if (![before.width, before.height, after.width, after.height].every((v) => Number.isSafeInteger(v) && v >= 224 && v <= 1280)
    || Math.abs(beforeAspect - afterAspect) / Math.max(beforeAspect, afterAspect) > 0.05) {
    throw new Error("Retake the pair with the same camera orientation and framing.");
  }
  const copies: OpaqueRgbaImage[] = [];
  let worker: Worker | undefined;
  try {
    copies.push(before.copyPixels());
    copies.push(after.copyPixels());
    for (const image of copies) {
      if (!validModelPixels(image.width, image.height, image.data)) throw new Error("The captured model input is invalid. Retake the photos.");
    }
    if (copies[0]!.data.every((value, index) => value === copies[1]!.data[index])) {
      throw new Error("These model views are identical. Capture distinct before and after photos.");
    }
    if (signal.aborted) throw new Error(CANCELLED);
    worker = new Worker(new URL("./inference.worker.ts", import.meta.url), { type: "module", name: "plategauge-experimental-estimator" });
    const ownedWorker = worker;
    return await new Promise<ExperimentalEstimate>((resolve, reject) => {
      let settled = false;
      const finish = (error?: Error, result?: ExperimentalEstimate) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal.removeEventListener("abort", abort);
        ownedWorker.onmessage = null; ownedWorker.onerror = null; ownedWorker.onmessageerror = null;
        ownedWorker.terminate();
        if (error) reject(error); else resolve(result!);
      };
      const abort = () => finish(new Error(CANCELLED));
      const timer = setTimeout(() => finish(new Error("Estimation took too long. Try again or use a more capable browser.")), TIMEOUT_MS);
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) { abort(); return; }
      ownedWorker.onmessage = (event: MessageEvent<unknown>) => {
        if (signal.aborted) { abort(); return; }
        if (isExperimentalEstimate(event.data)) finish(undefined, event.data);
        else finish(new Error("The local model could not produce a valid estimate. Try again; no result was kept."));
      };
      ownedWorker.onerror = () => finish(new Error("The browser model stopped unexpectedly. Try again."));
      ownedWorker.onmessageerror = () => finish(new Error("The browser could not read the model result. Try again."));
      try {
        ownedWorker.postMessage({ before: copies[0], after: copies[1] }, copies.map((image) => image.data.buffer as ArrayBuffer));
      } catch {
        finish(new Error("The browser could not prepare the model request. Try again."));
      }
    });
  } finally {
    worker?.terminate();
    // Successfully transferred buffers are detached. Clear only copies still owned here.
    for (const image of copies) if (image.data.byteLength) image.data.fill(0);
  }
}
