import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OpaqueRgbaImage } from "../libv2/pillowResize";
import type * as TensorPreprocess from "../lib/tensorPreprocess";
import { EXPERIMENTAL_MODEL } from "./contract";

const runtime = vi.hoisted(() => {
  const wasm: { numThreads?: number; proxy?: boolean; wasmPaths?: string } = {};
  return {
  run: vi.fn(),
  release: vi.fn(),
  create: vi.fn(),
  tensors: [] as { type: string; data: Float32Array; dims: number[]; dispose: ReturnType<typeof vi.fn> }[],
  wasm,
  invalidNormalized: false,
  inputNames: ["before", "after"],
  outputNames: ["quantiles"],
  };
});

vi.mock("onnxruntime-web/wasm", () => ({
  env: { wasm: runtime.wasm },
  Tensor: class {
    dispose = vi.fn();
    constructor(readonly type: string, readonly data: Float32Array, readonly dims: number[]) {
      runtime.tensors.push(this);
    }
  },
  InferenceSession: { create: runtime.create },
}));

vi.mock("../lib/tensorPreprocess", async (importOriginal) => {
  const original = await importOriginal<typeof TensorPreprocess>();
  return {
    ...original,
    rgbaToNormalizedChw: (pixels: Uint8ClampedArray) => runtime.invalidNormalized
      ? new Float32Array(3 * 224 * 224).fill(Number.NaN)
      : original.rgbaToNormalizedChw(pixels),
  };
});

function image(seed = 1): OpaqueRgbaImage {
  const data = new Uint8ClampedArray(224 * 224 * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = seed; data[i + 1] = seed * 2; data[i + 2] = seed * 3; data[i + 3] = 255;
  }
  return { width: 224, height: 224, data };
}

function output(data: unknown = new Float32Array([0.1, 0.25, 0.9]), dims = [1, 3]) {
  return { data, dims, dispose: vi.fn() };
}

async function startWorker(hostname = "localhost", protocol = "http:", secureContext = true) {
  let listener!: (event: MessageEvent<unknown>) => void;
  const postMessage = vi.fn();
  const close = vi.fn();
  vi.stubGlobal("self", {
    location: { hostname, origin: `${protocol}//${hostname}`, protocol },
    isSecureContext: secureContext,
    addEventListener: (type: string, callback: typeof listener) => {
      expect(type).toBe("message"); listener = callback;
    },
    postMessage,
    close,
  });
  const model = new ArrayBuffer(EXPERIMENTAL_MODEL.bytes);
  const arrayBuffer = vi.fn(() => Promise.resolve(model));
  const fetchMock = vi.fn(() => {
    let sent = false;
    return Promise.resolve({ ok: true, status: 200, type: "basic", redirected: false,
      url: `${protocol}//${hostname}/plategauge/models/plategauge.onnx`,
      headers: new Headers({ "Content-Type": "application/octet-stream" }),
      body: { getReader: () => ({
        read: async () => {
          if (sent) return { done: true };
          sent = true;
          return { done: false, value: new Uint8Array(await arrayBuffer()) };
        }, cancel: vi.fn().mockResolvedValue(undefined), releaseLock: vi.fn(),
      }) },
    } as unknown as Response);
  });
  const digestBytes = Uint8Array.from(EXPERIMENTAL_MODEL.sha256.match(/../g)!, (pair) => Number.parseInt(pair, 16));
  const digest = vi.fn(() => Promise.resolve(digestBytes.buffer));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("crypto", { subtle: { digest } });
  await import("./inference.worker");
  return {
    model, arrayBuffer, fetchMock, digest, postMessage, close,
    send: (request: unknown) => listener({ data: request } as MessageEvent<unknown>),
    done: async () => { await vi.waitFor(() => expect(close).toHaveBeenCalledOnce()); },
  };
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("DEV", true);
  vi.stubEnv("BASE_URL", "/plategauge/");
  vi.stubEnv("VITE_PLATEGAUGE_TEST_MODEL", "");
  vi.stubEnv("VITE_PLATEGAUGE_CAMERA_CANDIDATE", "");
  runtime.run.mockReset().mockResolvedValue({ quantiles: output() });
  runtime.release.mockReset().mockResolvedValue(undefined);
  runtime.create.mockReset().mockImplementation(() => Promise.resolve({
    run: runtime.run, release: runtime.release,
    inputNames: runtime.inputNames, outputNames: runtime.outputNames,
  }));
  runtime.tensors.length = 0;
  runtime.invalidNormalized = false;
  runtime.inputNames = ["before", "after"];
  runtime.outputNames = ["quantiles"];
  for (const key of Object.keys(runtime.wasm)) delete runtime.wasm[key as keyof typeof runtime.wasm];
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("experimental worker boundaries with synthetic pixels and mocked runtime only", () => {
  it("uses the pinned local model and raw median even when the old test-model flag is set", async () => {
    vi.stubEnv("VITE_PLATEGAUGE_TEST_MODEL", "1");
    const result = output();
    const extra = output(new Float32Array([9]), [1]);
    runtime.run.mockResolvedValue({ quantiles: result, extra });
    const worker = await startWorker();
    const before = image(2), after = image(3);
    worker.send({ before, after });
    await worker.done();
    expect(worker.fetchMock).toHaveBeenCalledOnce();
    expect(worker.fetchMock).toHaveBeenCalledWith(new URL("http://localhost/plategauge/models/plategauge.onnx"), {
      method: "GET", mode: "same-origin", cache: "force-cache", credentials: "omit", redirect: "error",
    });
    expect(worker.digest).toHaveBeenCalledWith("SHA-256", worker.model);
    expect(runtime.create).toHaveBeenCalledWith(worker.model, { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
    expect(runtime.wasm).toEqual({ numThreads: 1, proxy: false, wasmPaths: "http://localhost/plategauge/ort/" });
    expect(runtime.run).toHaveBeenCalledOnce();
    expect(runtime.run).toHaveBeenCalledWith({ before: runtime.tensors[0], after: runtime.tensors[1] });
    expect(worker.postMessage).toHaveBeenCalledOnce();
    const payload = worker.postMessage.mock.calls[0]![0] as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual(["leftoverFraction", "modelVersion", "processingMs"]);
    expect(payload).toMatchObject({ leftoverFraction: 0.25, modelVersion: EXPERIMENTAL_MODEL.version });
    expect(payload.processingMs).toEqual(expect.any(Number));
    expect(Number(payload.processingMs)).toBeGreaterThanOrEqual(0);
    expect(runtime.tensors).toHaveLength(2);
    for (const tensor of runtime.tensors) {
      expect(tensor.type).toBe("float32"); expect(tensor.dims).toEqual([1, 3, 224, 224]);
      expect(tensor.dispose).toHaveBeenCalledOnce(); expect(tensor.data.every((v) => v === 0)).toBe(true);
    }
    expect(result.dispose).toHaveBeenCalledOnce(); expect(extra.dispose).toHaveBeenCalledOnce();
    expect(before.data.every((v) => v === 0)).toBe(true); expect(after.data.every((v) => v === 0)).toBe(true);
    expect(runtime.release).toHaveBeenCalledOnce();
  });

  it.each(["example.com", "localhost.example.com", "192.168.1.2"])("rejects non-loopback host %s before any fetch", async (hostname) => {
    const worker = await startWorker(hostname);
    worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(worker.fetchMock).not.toHaveBeenCalled(); expect(runtime.create).not.toHaveBeenCalled();
    expect(worker.postMessage).toHaveBeenCalledWith({ error: "estimation_unavailable" });
  });

  it("rejects a production context before any fetch", async () => {
    vi.stubEnv("DEV", false);
    const worker = await startWorker();
    worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(worker.fetchMock).not.toHaveBeenCalled(); expect(runtime.run).not.toHaveBeenCalled();
  });

  it("allows an explicit secure candidate on the exact approved HTTPS hostname", async () => {
    vi.stubEnv("DEV", false); vi.stubEnv("VITE_PLATEGAUGE_CAMERA_CANDIDATE", "1");
    const worker = await startWorker("aldaqrouqtaysir.github.io", "https:");
    worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(runtime.run).toHaveBeenCalledOnce();
    expect(worker.fetchMock).toHaveBeenCalledWith(new URL("https://aldaqrouqtaysir.github.io/plategauge/models/plategauge.onnx"), expect.objectContaining({ mode: "same-origin" }));
  });

  it.each([
    ["aldaqrouqtaysir.github.io", "http:", true, "1"],
    ["aldaqrouqtaysir.github.io.evil.example", "https:", true, "1"],
    ["localhost", "https:", false, "1"],
    ["localhost", "file:", true, "1"],
    ["aldaqrouqtaysir.github.io", "https:", true, "true"],
  ] as const)("rejects unsafe candidate context %s %s %s %s", async (hostname, protocol, secure, flag) => {
    vi.stubEnv("DEV", false); vi.stubEnv("VITE_PLATEGAUGE_CAMERA_CANDIDATE", flag);
    const worker = await startWorker(hostname, protocol, secure);
    worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(worker.fetchMock).not.toHaveBeenCalled(); expect(runtime.run).not.toHaveBeenCalled();
  });

  it.each(["https://example.com/app/", "//example.com/app/", "http://user:password@localhost/app/"])("rejects unsafe model/runtime base %s before network access", async (base) => {
    vi.stubEnv("BASE_URL", base);
    const worker = await startWorker();
    worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(worker.fetchMock).not.toHaveBeenCalled(); expect(runtime.create).not.toHaveBeenCalled();
    expect(worker.postMessage).toHaveBeenCalledWith({ error: "estimation_unavailable" });
  });

  it.each([null, {}, { before: image(), after: null }, { before: image(), after: { width: 1, height: 1, data: new Uint8ClampedArray(4) } }])("rejects malformed image request %# before loading a model", async (request) => {
    const worker = await startWorker(); worker.send(request); await worker.done();
    expect(worker.fetchMock).not.toHaveBeenCalled(); expect(runtime.run).not.toHaveBeenCalled();
    expect(worker.postMessage).toHaveBeenCalledWith({ error: "estimation_unavailable" });
  });

  it("rejects nonopaque input and wipes valid input copies", async () => {
    const before = image(), after = image(2); after.data[3] = 0;
    const worker = await startWorker(); worker.send({ before, after }); await worker.done();
    expect(worker.fetchMock).not.toHaveBeenCalled();
    expect(before.data.every((v) => v === 0)).toBe(true); expect(after.data.every((v) => v === 0)).toBe(true);
  });

  it.each(["size", "checksum", "http", "body"])("rejects model %s failure before runtime initialization", async (failure) => {
    const worker = await startWorker();
    if (failure === "size") worker.arrayBuffer.mockResolvedValue(new ArrayBuffer(3));
    if (failure === "checksum") worker.digest.mockResolvedValue(new Uint8Array(32).buffer);
    if (failure === "http") worker.fetchMock.mockResolvedValue({ ok: false } as Response);
    if (failure === "body") worker.arrayBuffer.mockRejectedValue(new Error("sensitive synthetic body detail"));
    worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(runtime.create).not.toHaveBeenCalled(); expect(runtime.run).not.toHaveBeenCalled();
    expect(worker.postMessage).toHaveBeenCalledWith({ error: "estimation_unavailable" });
    if (failure === "size") expect(worker.digest).not.toHaveBeenCalled();
  });

  it.each(["input", "output"])("rejects a mismatched %s name contract and releases the session", async (kind) => {
    if (kind === "input") runtime.inputNames = ["image"]; else runtime.outputNames = ["prediction"];
    const worker = await startWorker(); worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(runtime.run).not.toHaveBeenCalled(); expect(runtime.release).toHaveBeenCalledOnce();
  });

  it("rejects a nonfinite normalized tensor before running inference", async () => {
    runtime.invalidNormalized = true;
    const worker = await startWorker(); worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(runtime.run).not.toHaveBeenCalled(); expect(runtime.tensors).toHaveLength(0);
    expect(runtime.release).toHaveBeenCalledOnce();
    expect(worker.postMessage).toHaveBeenCalledWith({ error: "estimation_unavailable" });
  });

  it.each([
    { label: "missing", value: undefined },
    { label: "shape", value: output(new Float32Array([0.1, 0.25, 0.9]), [3]) },
    { label: "type", value: output(new Float64Array([0.1, 0.25, 0.9])) },
    { label: "extra value", value: output(new Float32Array([0.1, 0.25, 0.9, 1])) },
    { label: "nonfinite", value: output(new Float32Array([0.1, Number.NaN, 0.9])) },
    { label: "order", value: output(new Float32Array([0.8, 0.2, 0.9])) },
    { label: "range", value: output(new Float32Array([-0.1, 0.2, 0.9])) },
  ])("rejects $label output without leaking model values", async ({ value }) => {
    runtime.run.mockResolvedValue(value ? { quantiles: value } : {});
    const worker = await startWorker(); worker.send({ before: image(), after: image(2) }); await worker.done();
    expect(worker.postMessage).toHaveBeenCalledWith({ error: "estimation_unavailable" });
    for (const tensor of runtime.tensors) { expect(tensor.dispose).toHaveBeenCalledOnce(); expect(tensor.data.every((v) => v === 0)).toBe(true); }
    if (value) expect(value.dispose).toHaveBeenCalledOnce();
    expect(runtime.release).toHaveBeenCalledOnce();
  });

  it.each(["create", "run"])("sanitizes a %s failure and releases every owned resource", async (phase) => {
    const before = image(), after = image(2);
    const failure = new Error("synthetic-private-device-name/photo-pixels/prediction=0.83");
    if (phase === "create") runtime.create.mockRejectedValue(failure); else runtime.run.mockRejectedValue(failure);
    const worker = await startWorker(); worker.send({ before, after }); await worker.done();
    expect(worker.postMessage).toHaveBeenCalledWith({ error: "estimation_unavailable" });
    expect(worker.postMessage).toHaveBeenCalledOnce();
    expect(before.data.every((v) => v === 0)).toBe(true); expect(after.data.every((v) => v === 0)).toBe(true);
    if (phase === "run") {
      for (const tensor of runtime.tensors) expect(tensor.dispose).toHaveBeenCalledOnce();
      expect(runtime.release).toHaveBeenCalledOnce();
    } else expect(runtime.release).not.toHaveBeenCalled();
  });

  it("accepts only the first request in its single-use worker", async () => {
    const worker = await startWorker();
    worker.send({ before: image(), after: image(2) });
    worker.send({ before: image(3), after: image(4) });
    await worker.done();
    expect(worker.fetchMock).toHaveBeenCalledOnce(); expect(runtime.run).toHaveBeenCalledOnce();
    expect(worker.postMessage).toHaveBeenCalledOnce();
  });

  it("rejects unknown request fields before loading the model", async () => {
    const worker = await startWorker(); worker.send({ before: image(), after: image(2), extra: "untrusted" }); await worker.done();
    expect(worker.fetchMock).not.toHaveBeenCalled();
  });

  it("continues cleanup when output disposal and session release both throw", async () => {
    const result = output(); result.dispose.mockImplementation(() => { throw new Error("synthetic dispose failure"); });
    runtime.run.mockResolvedValue({ quantiles: result }); runtime.release.mockRejectedValue(new Error("synthetic release failure"));
    const worker = await startWorker(), before = image(), after = image(2);
    worker.send({ before, after }); await worker.done();
    expect(runtime.release).toHaveBeenCalledOnce();
    for (const tensor of runtime.tensors) expect(tensor.data.every((value) => value === 0)).toBe(true);
    expect(before.data.every((value) => value === 0)).toBe(true);
    expect(after.data.every((value) => value === 0)).toBe(true);
  });
});
