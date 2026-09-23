import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CAMERA_LIMITS, CameraError, cameraErrorMessage, captureFrame, requestCamera, stopStream } from "./camera";
import type { CameraFacing } from "./camera";
import { LOCAL_OPERATION_TIMEOUT_MS } from "../capturePrototype/operations";
import { preparePillowCrop, type OpaqueRgbaImage } from "../libv2/pillowResize";

vi.mock("../libv2/pillowResize", () => ({ preparePillowCrop: vi.fn() }));

function streamFixture(videoState: MediaStreamTrackState = "live", audioCount = 0) {
  const videoStop = vi.fn();
  const audioStops = Array.from({ length: audioCount }, () => vi.fn());
  const videoTracks = [{ kind: "video", readyState: videoState, enabled: true, muted: false, stop: videoStop }];
  const audioTracks = audioStops.map((stop) => ({ kind: "audio", readyState: "live", stop }));
  const stream = {
    getTracks: () => [...videoTracks, ...audioTracks],
    getVideoTracks: () => videoTracks,
    getAudioTracks: () => audioTracks,
  } as unknown as MediaStream;
  return { stream, videoStop, audioStops };
}

function videoFixture(width = 1920, height = 1080, readyState = 2): HTMLVideoElement {
  const video = document.createElement("video");
  Object.defineProperties(video, {
    videoWidth: { configurable: true, value: width },
    videoHeight: { configurable: true, value: height },
    readyState: { configurable: true, value: readyState },
    srcObject: { configurable: true, value: streamFixture().stream },
  });
  return video;
}

function canvasFixture(stall = false) {
  const context = { drawImage: vi.fn(), imageSmoothingEnabled: false, imageSmoothingQuality: "low",
    getImageData: vi.fn((_x: number, _y: number, width: number, height: number) => ({ data: new Uint8ClampedArray(width * height * 4).fill(255) })),
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  const state: { canvas: HTMLCanvasElement | null; callback: BlobCallback | null } = { canvas: null, callback: null };
  const blob = new Blob(["synthetic JPEG encoder output"], { type: "image/jpeg" });
  const encode = vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (this: HTMLCanvasElement, callback) {
    state.canvas = this; state.callback = callback;
    if (!stall) callback(blob);
  });
  return { context, state, encode, blob, complete(value: Blob | null) {
    if (!state.callback) throw new Error("No mock encoder callback.");
    state.callback(value);
  } };
}

const getUserMedia = vi.fn<(constraints: MediaStreamConstraints) => Promise<MediaStream>>();
const createUrl = vi.fn(() => "blob:local-camera-photo");
const revokeUrl = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(preparePillowCrop).mockImplementation(() => Promise.resolve({ width: 224, height: 224, data: new Uint8ClampedArray(224 * 224 * 4).fill(255) }));
  vi.stubGlobal("isSecureContext", true);
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeUrl });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("explicit, video-only camera requests (mock hardware only)", () => {
  it("returns a live stream with bounded rear-facing preferences and no audio", async () => {
    const fixture = streamFixture(); getUserMedia.mockResolvedValueOnce(fixture.stream);
    expect(await requestCamera(new AbortController().signal)).toBe(fixture.stream);
    expect(getUserMedia).toHaveBeenCalledExactlyOnceWith({ audio: false, video: { facingMode: { ideal: "environment" }, width: { ideal: 1280, max: 1280 }, height: { ideal: 960, max: 960 } } });
    expect(fixture.videoStop).not.toHaveBeenCalled();
  });
  it("accepts the user-facing preference without enumerating devices", async () => {
    getUserMedia.mockResolvedValueOnce(streamFixture().stream);
    await requestCamera(new AbortController().signal, "user");
    expect(getUserMedia).toHaveBeenCalledExactlyOnceWith({ audio: false, video: { facingMode: { ideal: "user" }, width: { ideal: 1280, max: 1280 }, height: { ideal: 960, max: 960 } } });
  });
  it("rejects insecure pages before asking for permission", async () => {
    vi.stubGlobal("isSecureContext", false);
    await expect(requestCamera(new AbortController().signal)).rejects.toMatchObject({ code: "insecure_context" });
    expect(getUserMedia).not.toHaveBeenCalled();
  });
  it("rejects unavailable APIs and invalid facing values", async () => {
    await expect(requestCamera(new AbortController().signal, "external" as CameraFacing)).rejects.toMatchObject({ code: "unsupported_constraints" });
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
    await expect(requestCamera(new AbortController().signal)).rejects.toMatchObject({ code: "camera_unavailable" });
    expect(getUserMedia).not.toHaveBeenCalled();
  });
  it.each([
    ["NotAllowedError", "permission_denied"], ["NotFoundError", "camera_missing"],
    ["NotReadableError", "camera_busy"], ["SecurityError", "security_restriction"],
    ["OverconstrainedError", "unsupported_constraints"], ["AbortError", "camera_busy"],
  ])("maps %s without exposing device details", async (name, code) => {
    getUserMedia.mockRejectedValueOnce(new DOMException("private camera device ID", name));
    const pending = requestCamera(new AbortController().signal);
    await expect(pending).rejects.toMatchObject({ code });
    await pending.catch((error: unknown) => expect(cameraErrorMessage(error)).not.toContain("private camera"));
  });
  it("does not request permission after pre-cancellation", async () => {
    const controller = new AbortController(); controller.abort();
    await expect(requestCamera(controller.signal)).rejects.toMatchObject({ code: "cancelled" });
    expect(getUserMedia).not.toHaveBeenCalled();
  });
  it("normalizes a synchronously thrown browser security failure", async () => {
    getUserMedia.mockImplementationOnce(() => { throw new DOMException("private device text", "SecurityError"); });
    await expect(requestCamera(new AbortController().signal)).rejects.toMatchObject({ code: "security_restriction" });
  });
  it("stops every track of a late permission grant after cancellation", async () => {
    const controller = new AbortController(); const fixture = streamFixture("live", 1);
    let grant!: (stream: MediaStream) => void;
    getUserMedia.mockReturnValueOnce(new Promise((resolve) => { grant = resolve; }));
    const pending = requestCamera(controller.signal);
    const failure = expect(pending).rejects.toMatchObject({ code: "cancelled" });
    controller.abort(); await failure;
    grant(fixture.stream); await Promise.resolve(); await Promise.resolve();
    expect(fixture.videoStop).toHaveBeenCalledOnce(); expect(fixture.audioStops[0]).toHaveBeenCalledOnce();
  });
  it("times out unresolved permission and stops a stream granted afterward", async () => {
    vi.useFakeTimers(); const fixture = streamFixture();
    let grant!: (stream: MediaStream) => void;
    getUserMedia.mockReturnValueOnce(new Promise((resolve) => { grant = resolve; }));
    const pending = requestCamera(new AbortController().signal);
    const failure = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(LOCAL_OPERATION_TIMEOUT_MS); await failure;
    grant(fixture.stream); await Promise.resolve(); await Promise.resolve();
    expect(fixture.videoStop).toHaveBeenCalledOnce(); expect(vi.getTimerCount()).toBe(0);
  });
  it("stops a promptly returned stream if cancellation wins before acceptance", async () => {
    const controller = new AbortController(); const fixture = streamFixture();
    getUserMedia.mockImplementationOnce(() => { queueMicrotask(() => controller.abort()); return Promise.resolve(fixture.stream); });
    await expect(requestCamera(controller.signal)).rejects.toMatchObject({ code: "cancelled" });
    expect(fixture.videoStop).toHaveBeenCalledOnce();
  });
  it.each(["ended", "audio"])("rejects and stops unsuitable streams: %s", async (kind) => {
    const fixture = streamFixture(kind === "ended" ? "ended" : "live", kind === "audio" ? 1 : 0);
    getUserMedia.mockResolvedValueOnce(fixture.stream);
    await expect(requestCamera(new AbortController().signal)).rejects.toMatchObject({ code: "camera_missing" });
    expect(fixture.videoStop).toHaveBeenCalledOnce();
    for (const stop of fixture.audioStops) expect(stop).toHaveBeenCalledOnce();
  });
  it("attempts every track even if one stop implementation throws", () => {
    const last = vi.fn();
    const stream = { getTracks: () => [{ stop: () => { throw new Error("bad track"); } }, { stop: last }] } as unknown as MediaStream;
    expect(() => stopStream(stream)).not.toThrow(); expect(last).toHaveBeenCalledOnce();
  });
});

describe("in-memory JPEG preview capture", () => {
  it.each([[1920, 1080, 1280, 720], [1080, 1920, 720, 1280], [640, 480, 640, 480]])("bounds %i×%i frames without upscaling", async (width, height, outputWidth, outputHeight) => {
    const encoder = canvasFixture(); const video = videoFixture(width, height);
    const photo = await captureFrame(video, new AbortController().signal);
    expect({ width: photo.width, height: photo.height }).toEqual({ width: outputWidth, height: outputHeight });
    expect(encoder.context.drawImage).toHaveBeenCalledWith(video, 0, 0, width, height);
    expect(encoder.context.drawImage).toHaveBeenCalledWith(expect.any(HTMLCanvasElement), 0, 0, outputWidth, outputHeight);
    expect(encoder.encode).toHaveBeenCalledWith(expect.any(Function), "image/jpeg", 0.9);
    expect(createUrl).toHaveBeenCalledExactlyOnceWith(encoder.blob);
    expect([encoder.state.canvas?.width, encoder.state.canvas?.height]).toEqual([0, 0]);
    expect(Object.keys(photo).sort()).toEqual(["copyPixels", "copyPreviewBlob", "height", "release", "url", "width"]);
    const snapshot = photo.copyPixels();
    expect(snapshot.data).toHaveLength(224 * 224 * 4);
    const retained = await (vi.mocked(preparePillowCrop).mock.results[0]!.value as Promise<OpaqueRgbaImage>);
    expect(snapshot.data).not.toBe(retained.data);
    photo.release(); photo.release(); expect(revokeUrl).toHaveBeenCalledExactlyOnceWith(photo.url);
    expect(retained.data.every((value) => value === 0)).toBe(true);
    expect(() => photo.copyPixels()).toThrow();
  });
  it.each([0, 1, NaN, Infinity, 2.5, 5])("rejects unready/invalid readyState %s before creating a Canvas", async (state) => {
    const video = videoFixture(640, 480, state); const create = vi.spyOn(document, "createElement");
    await expect(captureFrame(video, new AbortController().signal)).rejects.toMatchObject({ code: "frame_not_ready" });
    expect(create).not.toHaveBeenCalled();
  });
  it.each(["missing", "blob", "ended", "muted", "disabled", "unknown-muted", "empty", "broken"])("rejects cached readyState with a %s camera source", async (kind) => {
    const video = videoFixture(640, 480, 4);
    const track = { readyState: kind === "ended" ? "ended" : "live", enabled: kind !== "disabled", muted: kind === "unknown-muted" ? undefined : kind === "muted" };
    const source = kind === "missing" ? null : kind === "blob" ? new Blob(["not a stream"]) : {
      getVideoTracks: () => {
        if (kind === "broken") throw new Error("bad stream");
        return kind === "empty" ? [] : [track];
      },
    };
    Object.defineProperty(video, "srcObject", { configurable: true, value: source });
    const create = vi.spyOn(document, "createElement");
    await expect(captureFrame(video, new AbortController().signal)).rejects.toMatchObject({ code: "frame_not_ready" });
    expect(create).not.toHaveBeenCalled(); expect(createUrl).not.toHaveBeenCalled();
  });
  it.each([[0, 480], [223, 480], [640, 223], [NaN, 480], [Infinity, 480], [640.5, 480]])("rejects invalid source size %s×%s", async (width, height) => {
    await expect(captureFrame(videoFixture(width, height), new AbortController().signal)).rejects.toMatchObject({ code: "invalid_frame" });
    expect(createUrl).not.toHaveBeenCalled();
  });
  it("rejects over-16MP frames before allocation", async () => {
    await expect(captureFrame(videoFixture(4001, 4000), new AbortController().signal)).rejects.toMatchObject({ code: "frame_too_large" });
    expect(createUrl).not.toHaveBeenCalled();
  });
  it("clears a Canvas on unavailable rendering or draw failure", async () => {
    const encoder = canvasFixture();
    encoder.context.drawImage.mockImplementation(() => { throw new Error("draw failed"); });
    const create = vi.spyOn(document, "createElement");
    await expect(captureFrame(videoFixture(), new AbortController().signal)).rejects.toMatchObject({ code: "encoding_failed" });
    const canvases = create.mock.results.map((result): unknown => result.value as unknown).filter((item): item is HTMLCanvasElement => item instanceof HTMLCanvasElement);
    expect(canvases).toHaveLength(1); expect([canvases[0]!.width, canvases[0]!.height]).toEqual([0, 0]);
    expect(createUrl).not.toHaveBeenCalled();
  });
  it("fails closed if a rendering context is unavailable", async () => {
    const video = videoFixture(); const create = vi.spyOn(document, "createElement");
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    await expect(captureFrame(video, new AbortController().signal)).rejects.toMatchObject({ code: "encoding_failed" });
    const canvases = create.mock.results.map((result): unknown => result.value as unknown).filter((item): item is HTMLCanvasElement => item instanceof HTMLCanvasElement);
    expect(canvases).toHaveLength(1); expect([canvases[0]!.width, canvases[0]!.height]).toEqual([0, 0]);
    expect(createUrl).not.toHaveBeenCalled();
  });
  it("clears the Canvas when object-URL allocation fails", async () => {
    const encoder = canvasFixture();
    createUrl.mockImplementationOnce(() => { throw new Error("allocation failed"); });
    await expect(captureFrame(videoFixture(), new AbortController().signal)).rejects.toMatchObject({ code: "encoding_failed" });
    expect([encoder.state.canvas?.width, encoder.state.canvas?.height]).toEqual([0, 0]);
    expect(revokeUrl).not.toHaveBeenCalled();
  });
  it.each(["null", "empty", "wrong-type", "oversized"])("rejects %s encoder output and clears Canvas", async (kind) => {
    const encoder = canvasFixture(true);
    const pending = captureFrame(videoFixture(), new AbortController().signal);
    await vi.waitFor(() => expect(encoder.state.callback).not.toBeNull());
    const output = kind === "null" ? null : new Blob([kind === "oversized" ? new Uint8Array(CAMERA_LIMITS.maximumPhotoBytes + 1) : kind === "empty" ? "" : "bytes"], { type: kind === "wrong-type" ? "image/png" : "image/jpeg" });
    encoder.complete(output);
    await expect(pending).rejects.toMatchObject({ code: kind === "oversized" ? "photo_too_large" : "encoding_failed" });
    expect([encoder.state.canvas?.width, encoder.state.canvas?.height]).toEqual([0, 0]); expect(createUrl).not.toHaveBeenCalled();
  });
  it("clears a hanging encoder on deadline and never publishes a late photo", async () => {
    vi.useFakeTimers(); const encoder = canvasFixture(true);
    const pending = captureFrame(videoFixture(), new AbortController().signal);
    const failure = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(LOCAL_OPERATION_TIMEOUT_MS); await failure;
    expect([encoder.state.canvas?.width, encoder.state.canvas?.height]).toEqual([0, 0]);
    encoder.complete(encoder.blob); await Promise.resolve(); await Promise.resolve();
    expect(createUrl).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
  });
  it("clears a pending capture immediately on cancellation and ignores the late callback", async () => {
    const encoder = canvasFixture(true); const controller = new AbortController();
    const pending = captureFrame(videoFixture(), controller.signal);
    await vi.waitFor(() => expect(encoder.state.callback).not.toBeNull());
    const failure = expect(pending).rejects.toMatchObject({ code: "cancelled" });
    controller.abort(); await failure;
    expect([encoder.state.canvas?.width, encoder.state.canvas?.height]).toEqual([0, 0]);
    encoder.complete(encoder.blob); await Promise.resolve(); await Promise.resolve();
    expect(createUrl).not.toHaveBeenCalled();
  });
  it("revokes a URL if cancellation happens during URL allocation", async () => {
    canvasFixture(); const controller = new AbortController();
    createUrl.mockImplementationOnce(() => { controller.abort(); return "blob:cancelled-photo"; });
    await expect(captureFrame(videoFixture(), controller.signal)).rejects.toMatchObject({ code: "cancelled" });
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith("blob:cancelled-photo");
  });
  it("bounds preprocessing, aborts its work and clears a late crop after timeout", async () => {
    vi.useFakeTimers(); canvasFixture();
    let resolve!: (image: OpaqueRgbaImage) => void;
    vi.mocked(preparePillowCrop).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const pending = captureFrame(videoFixture(640, 480), new AbortController().signal);
    const failure = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(LOCAL_OPERATION_TIMEOUT_MS); await failure;
    expect(vi.mocked(preparePillowCrop).mock.calls[0]![1]!.signal!.aborted).toBe(true);
    const late = { width: 224, height: 224, data: new Uint8ClampedArray(224 * 224 * 4).fill(255) };
    resolve(late); await Promise.resolve(); await Promise.resolve();
    expect(late.data.every((value) => value === 0)).toBe(true);
    expect(createUrl).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
  });
  it("does not capture after pre-cancellation", async () => {
    const video = videoFixture(); const controller = new AbortController(); controller.abort();
    const create = vi.spyOn(document, "createElement");
    await expect(captureFrame(video, controller.signal)).rejects.toMatchObject({ code: "cancelled" });
    expect(create).not.toHaveBeenCalled(); expect(createUrl).not.toHaveBeenCalled();
  });
  it("uses no network, files, storage, worker, or model API", async () => {
    canvasFixture(); const forbidden = vi.fn(() => { throw new Error("Forbidden side effect"); });
    vi.stubGlobal("fetch", forbidden); vi.stubGlobal("XMLHttpRequest", forbidden);
    vi.stubGlobal("File", forbidden); vi.stubGlobal("Worker", forbidden);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(forbidden);
    const photo = await captureFrame(videoFixture(), new AbortController().signal); photo.release();
    expect(forbidden).not.toHaveBeenCalled(); expect(getUserMedia).not.toHaveBeenCalled();
  });
});

it("returns bounded messages for unknown failures rather than arbitrary error text", () => {
  expect(cameraErrorMessage(new Error("secret device label"))).not.toContain("secret");
  expect(cameraErrorMessage(new CameraError("permission_denied"))).toContain("permission");
});
