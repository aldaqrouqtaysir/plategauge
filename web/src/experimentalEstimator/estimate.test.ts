import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { estimatePair } from "./estimate";
import { EXPERIMENTAL_MODEL, experimentalContextAllowed, isExperimentalEstimate, medianFromOutput, validModelPixels } from "./contract";

function pixels(red = 1) {
  const data = new Uint8ClampedArray(224 * 224 * 4).fill(255);
  data[0] = red;
  return { width: 224, height: 224, data };
}
function photo(red = 1) {
  const image = pixels(red);
  return { width: 640, height: 480, url: "blob:generated-test-only", release: vi.fn(), copyPixels: vi.fn(() => image) };
}
const result = { leftoverFraction: 0.4, modelVersion: EXPERIMENTAL_MODEL.version, processingMs: 300 };
class MockWorker {
  static instances: MockWorker[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessageerror: (() => void) | null = null;
  postMessage = vi.fn();
  terminate = vi.fn();
  constructor() { MockWorker.instances.push(this); }
  reply(value: unknown) { this.onmessage?.({ data: value } as MessageEvent); }
}
beforeEach(() => {
  MockWorker.instances = [];
  vi.stubGlobal("Worker", MockWorker);
  vi.stubGlobal("location", new URL("http://127.0.0.1/"));
  vi.stubEnv("DEV", true);
  vi.stubEnv("VITE_PLATEGAUGE_CAMERA_CANDIDATE", "");
  vi.stubGlobal("isSecureContext", true);
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("local estimator contract", () => {
  it.each([
    [false, "aldaqrouqtaysir.github.io", "https:", true, true, true],
    [false, "aldaqrouqtaysir.github.io", "http:", true, true, false],
    [false, "localhost", "http:", true, true, true],
    [false, "127.0.0.1", "https:", true, true, true],
    [false, "[::1]", "http:", true, true, true],
    [false, "localhost", "http:", false, true, false],
    [true, "localhost", "file:", true, false, false],
    [true, "localhost", "https:", false, false, false],
    [true, "aldaqrouqtaysir.github.io", "https:", true, false, false],
    [false, "aldaqrouqtaysir.github.io.evil.test", "https:", true, true, false],
    [false, "other.github.io", "https:", true, true, false],
  ] as const)("checks explicit context %#", (dev, host, protocol, secureContext, candidate, expected) => {
    expect(experimentalContextAllowed(dev, host, { protocol, secureContext, candidate })).toBe(expected);
  });
  it.each(["127.0.0.1", "localhost", "::1", "[::1]"])("allows only local development: %s", (host) => {
    expect(experimentalContextAllowed(true, host)).toBe(true);
    expect(experimentalContextAllowed(false, host)).toBe(false);
  });
  it.each(["evil.localhost", "127.0.0.1.example.com", "example.com", "0.0.0.0", ""])("rejects %s", (host) => expect(experimentalContextAllowed(true, host)).toBe(false));
  it("validates output without applying calibration or computing confidence", () => {
    expect(medianFromOutput([0.1, 0.4, 0.9])).toBe(0.4);
    expect(medianFromOutput([0, 0, 1])).toBe(0);
    expect(isExperimentalEstimate(result)).toBe(true);
  });
  it.each([[], [0, 1], [0, NaN, 1], [0.5, 0.4, 1], [0, 0.9, 0.8], [-0.01, 0, 1], [0, 1, 1.1]].map((values) => ({ values })))("rejects malformed quantiles $values", ({ values }) => expect(() => medianFromOutput(values)).toThrow());
  it.each([null, {}, { ...result, modelVersion: "test-adapter" }, { ...result, leftoverFraction: NaN }, { ...result, leftoverFraction: -1 }, { ...result, processingMs: Infinity }])("rejects unknown worker result %j", (value) => expect(isExperimentalEstimate(value)).toBe(false));
  it("validates dimensions, opaque bytes, and buffer ownership", () => {
    const image = pixels();
    expect(validModelPixels(224, 224, image.data)).toBe(true);
    expect(validModelPixels(223, 224, image.data)).toBe(false);
    expect(validModelPixels(224, 224, new Float32Array(image.data.length))).toBe(false);
    expect(validModelPixels(224, 224, new Uint8ClampedArray(4))).toBe(false);
    expect(validModelPixels(224, 224, new Uint8ClampedArray(new ArrayBuffer(image.data.length + 1), 1))).toBe(false);
    image.data[3] = 0;
    expect(validModelPixels(224, 224, image.data)).toBe(false);
  });
});

describe("explicit one-shot worker ownership (generated pixels and mocked worker)", () => {
  it("permits the explicit secure candidate but rejects truthy non-one flags", async () => {
    vi.stubEnv("DEV", false); vi.stubGlobal("location", new URL("https://aldaqrouqtaysir.github.io/plategauge/"));
    vi.stubEnv("VITE_PLATEGAUGE_CAMERA_CANDIDATE", "true");
    await expect(estimatePair(photo(), photo(2), new AbortController().signal)).rejects.toThrow("secure");
    expect(MockWorker.instances).toHaveLength(0);
    vi.stubEnv("VITE_PLATEGAUGE_CAMERA_CANDIDATE", "1");
    const pending = estimatePair(photo(), photo(2), new AbortController().signal);
    MockWorker.instances[0]!.reply(result); expect(await pending).toEqual(result);
  });
  it("rejects an insecure context and result payloads with unknown fields", async () => {
    vi.stubGlobal("isSecureContext", false);
    await expect(estimatePair(photo(), photo(2), new AbortController().signal)).rejects.toThrow("secure");
    expect(MockWorker.instances).toHaveLength(0);
    expect(isExperimentalEstimate({ ...result, confidence: 0.99 })).toBe(false);
  });
  it("returns a pinned result then terminates worker and clears owned copies", async () => {
    const before = photo(1), after = photo(2);
    const pending = estimatePair(before, after, new AbortController().signal);
    const worker = MockWorker.instances[0]!;
    expect(worker.postMessage).toHaveBeenCalledOnce();
    worker.reply(result);
    expect(await pending).toEqual(result);
    expect(worker.terminate).toHaveBeenCalled();
    expect(before.copyPixels().data.every((v) => v === 0)).toBe(true);
    expect(worker.onmessage).toBeNull();
    expect(before.release).not.toHaveBeenCalled();
  });
  it("blocks production, remote origin and pre-cancelled calls without a worker", async () => {
    vi.stubEnv("DEV", false);
    await expect(estimatePair(photo(), photo(2), new AbortController().signal)).rejects.toThrow("local");
    vi.stubEnv("DEV", true); vi.stubGlobal("location", new URL("http://example.com/"));
    await expect(estimatePair(photo(), photo(2), new AbortController().signal)).rejects.toThrow("local");
    vi.stubGlobal("location", new URL("http://localhost/"));
    const abort = new AbortController(); abort.abort();
    await expect(estimatePair(photo(), photo(2), abort.signal)).rejects.toThrow("cancelled");
    expect(MockWorker.instances).toHaveLength(0);
  });
  it("rejects same-image, invalid pixel and mismatched shape inputs", async () => {
    const signal = new AbortController().signal;
    await expect(estimatePair(photo(), photo(), signal)).rejects.toThrow("identical");
    await expect(estimatePair(photo(), { ...photo(2), width: 224 }, signal)).rejects.toThrow("orientation");
    const malformed = photo(2); malformed.copyPixels.mockReturnValue({ ...pixels(), height: 0 });
    await expect(estimatePair(photo(), malformed, signal)).rejects.toThrow("invalid");
    expect(MockWorker.instances).toHaveLength(0);
  });
  it("preserves allowlisted preflight codes for actionable UI recovery", async () => {
    const signal = new AbortController().signal;
    await expect(estimatePair(photo(), photo(), signal)).rejects.toMatchObject({ code: "identical_pair" });
    await expect(estimatePair(photo(), { ...photo(2), width: 224 }, signal)).rejects.toMatchObject({ code: "mismatched_shape" });
    const malformed = photo(2); malformed.copyPixels.mockReturnValue({ ...pixels(), height: 0 });
    await expect(estimatePair(photo(), malformed, signal)).rejects.toMatchObject({ code: "invalid_input" });
    expect(MockWorker.instances).toHaveLength(0);
  });
  it("cleans a first copy when the second photo was released", async () => {
    const before = photo(), after = photo(2);
    after.copyPixels.mockImplementation(() => { throw new Error("released"); });
    await expect(estimatePair(before, after, new AbortController().signal)).rejects.toThrow("released");
    expect(before.copyPixels().data.every((v) => v === 0)).toBe(true);
  });
  it("terminates on abort and ignores a saved late response callback", async () => {
    const abort = new AbortController();
    const pending = estimatePair(photo(), photo(2), abort.signal);
    const worker = MockWorker.instances[0]!;
    const late = worker.onmessage!;
    abort.abort();
    await expect(pending).rejects.toThrow("cancelled");
    late({ data: result } as MessageEvent);
    expect(worker.terminate).toHaveBeenCalled();
  });
  it("bounds an unresponsive runtime", async () => {
    vi.useFakeTimers();
    const pending = estimatePair(photo(), photo(2), new AbortController().signal);
    const failure = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(60_000); await failure;
    expect(MockWorker.instances[0]!.terminate).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
  it.each(["onerror", "onmessageerror"] as const)("sanitizes %s and cleans resources", async (key) => {
    const pending = estimatePair(photo(), photo(2), new AbortController().signal);
    MockWorker.instances[0]![key]!();
    await expect(pending).rejects.toThrow("browser");
    expect(MockWorker.instances[0]!.terminate).toHaveBeenCalled();
  });
  it("fails closed for a synthetic/test-adapter result", async () => {
    const pending = estimatePair(photo(), photo(2), new AbortController().signal);
    MockWorker.instances[0]!.reply({ ...result, modelVersion: "test-adapter/not-a-model" });
    await expect(pending).rejects.toThrow("valid estimate");
  });
  it("cleans after worker construction or transfer failure", async () => {
    vi.stubGlobal("Worker", class { constructor() { throw new Error("unavailable"); } });
    await expect(estimatePair(photo(), photo(2), new AbortController().signal)).rejects.toThrow("unavailable");
    vi.stubGlobal("Worker", class extends MockWorker { override postMessage = vi.fn(() => { throw new Error("transfer"); }); });
    await expect(estimatePair(photo(), photo(2), new AbortController().signal)).rejects.toThrow("prepare");
    expect(MockWorker.instances[0]!.terminate).toHaveBeenCalled();
  });
});
