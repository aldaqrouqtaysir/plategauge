/// <reference types="node" />
import { Blob as NodeBlob, Buffer, File as NodeFile } from "node:buffer";
import { createHash, webcrypto } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LOCAL_OPERATION_TIMEOUT_MS } from "../capturePrototype/operations";
import { captureFrame, type CameraPhoto } from "./camera";
import {
  createSessionFile, releaseRestoredSession, restoreSessionFile, SESSION_COMPATIBILITY,
  SESSION_FILE_ACCEPT, SESSION_MAX_BYTES, SessionError, sessionErrorMessage,
} from "./session";

type PhotoRecord = { width: number; height: number; previewJpegBase64: string; cropRgbaBase64: string };
type FixtureRecord = {
  format: string; version: number; compatibility: Record<string, string>;
  before: PhotoRecord; after: PhotoRecord | null; startingMass: string; checksum: string;
};
const controller = () => new AbortController();
const bitmap = vi.fn<(blob: Blob) => Promise<ImageBitmap>>();
const createUrl = vi.fn(() => "blob:synthetic-session");
const revokeUrl = vi.fn();
const closes: ReturnType<typeof vi.fn>[] = [];

/** Synthetic marker stream; browser decode is mocked here, exercised genuinely in browser tests. */
function jpeg(width = 640, height = 480): Uint8Array<ArrayBuffer> {
  return new Uint8Array([
    0xff, 0xd8, 0xff, 0xc0, 0, 17, 8, height >> 8, height & 255, width >> 8, width & 255, 3,
    1, 0x11, 0, 2, 0x11, 0, 3, 0x11, 0,
    0xff, 0xda, 0, 12, 3, 1, 0, 2, 0, 3, 0, 0, 63, 0, 0, 0xff, 0xd9,
  ]);
}
function pixels(seed = 5): Uint8ClampedArray<ArrayBuffer> {
  return Uint8ClampedArray.from({ length: 224 * 224 * 4 }, (_, index) => index % 4 === 3 ? 255 : (index + seed) % 251);
}
function b64(value: Uint8Array | Uint8ClampedArray): string { return Buffer.from(value).toString("base64"); }
function hash(value: Uint8Array | Uint8ClampedArray): string { return createHash("sha256").update(value).digest("hex"); }
function photo(seed = 5, width = 640, height = 480) {
  const original = pixels(seed);
  const copies: Uint8ClampedArray[] = [];
  const blob = new Blob([jpeg(width, height)], { type: "image/jpeg" });
  const result = {
    url: `blob:owned-synthetic-${seed}`, width, height,
    copyPixels: vi.fn(() => {
      const data = new Uint8ClampedArray(original); copies.push(data);
      return { width: 224, height: 224, data };
    }),
    copyPreviewBlob: vi.fn(() => blob.slice(0, blob.size, blob.type)), release: vi.fn(),
  } satisfies CameraPhoto;
  return { photo: result, original, copies, blob };
}
function unsigned(pair = true): Omit<FixtureRecord, "checksum"> {
  const encoded = (seed: number): PhotoRecord => ({
    width: 640, height: 480, previewJpegBase64: b64(jpeg()), cropRgbaBase64: b64(pixels(seed)),
  });
  return { format: "plategauge-session", version: 1, compatibility: { ...SESSION_COMPATIBILITY },
    before: encoded(5), after: pair ? encoded(25) : null, startingMass: pair ? "250.50" : "" };
}
function fixture(pair = true): FixtureRecord {
  const value = unsigned(pair);
  return { ...value, checksum: createHash("sha256").update(JSON.stringify(value)).digest("hex") };
}
function rehash(value: FixtureRecord): FixtureRecord {
  const content = { ...value }; Reflect.deleteProperty(content, "checksum");
  return { ...value, checksum: createHash("sha256").update(JSON.stringify(content)).digest("hex") };
}
function file(value: unknown = fixture(), name = "plate.plategauge.json", type = "application/json"): File {
  return new File([JSON.stringify(value)], name, { type });
}
function read(value: FixtureRecord) { return restoreSessionFile(file(rehash(value)), controller().signal); }

beforeEach(() => {
  vi.clearAllMocks(); closes.length = 0;
  vi.stubGlobal("Blob", NodeBlob); vi.stubGlobal("File", NodeFile);
  vi.stubGlobal("crypto", webcrypto);
  vi.stubGlobal("createImageBitmap", bitmap);
  vi.stubGlobal("fetch", vi.fn(() => { throw new Error("Network forbidden"); }));
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeUrl });
  createUrl.mockImplementation(() => `blob:synthetic-session-${createUrl.mock.calls.length}`);
  bitmap.mockImplementation(async (blob) => {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    const close = vi.fn(); closes.push(close);
    return { width: bytes[9]! * 256 + bytes[10]!, height: bytes[7]! * 256 + bytes[8]!, close };
  });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("explicit local session round trips (synthetic bytes only)", () => {
  it("round trips both exact model crops, JPEG previews and entered mass without results", async () => {
    const before = photo(); const after = photo(25);
    const storage = vi.spyOn(Storage.prototype, "setItem");
    const blob = await createSessionFile({ before: before.photo, after: after.photo, startingMass: "250.50" }, controller().signal);
    expect(blob.type).toBe("application/json"); expect(blob.size).toBeLessThan(SESSION_MAX_BYTES);
    const document = JSON.parse(await blob.text()) as FixtureRecord;
    expect(Object.keys(document)).toEqual(["format", "version", "compatibility", "before", "after", "startingMass", "checksum"]);
    expect(document).toEqual(fixture());
    expect(Object.keys(document.before)).toEqual(["width", "height", "previewJpegBase64", "cropRgbaBase64"]);
    const restored = await restoreSessionFile(new File([blob], `saved${SESSION_FILE_ACCEPT}`, { type: blob.type }), controller().signal);
    expect(restored.startingMass).toBe("250.50");
    expect(hash(restored.before.copyPixels().data)).toBe(hash(before.original));
    expect(hash(restored.after!.copyPixels().data)).toBe(hash(after.original));
    expect(await restored.before.copyPreviewBlob!().arrayBuffer()).toEqual(await before.blob.arrayBuffer());
    expect(before.copies.every((copy) => copy.every((value) => value === 0))).toBe(true);
    expect(after.copies.every((copy) => copy.every((value) => value === 0))).toBe(true);
    expect(before.original.some((value) => value !== 0)).toBe(true);
    expect(before.photo.release).not.toHaveBeenCalled(); expect(after.photo.release).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled(); expect(storage).not.toHaveBeenCalled();
    releaseRestoredSession(restored);
    expect(revokeUrl).toHaveBeenCalledTimes(2); expect(closes.every((close) => close.mock.calls.length === 1)).toBe(true);
  });
  it("supports before-only sessions and trimmed optional mass", async () => {
    const blob = await createSessionFile({ before: photo().photo, after: null, startingMass: "  " }, controller().signal);
    const restored = await restoreSessionFile(new File([blob], "UPPER.PLATEGAUGE.JSON"), controller().signal);
    expect(restored.after).toBeNull(); expect(restored.startingMass).toBe("");
    releaseRestoredSession(restored);
  });
  it("retains the existing 64-character mass boundary with exact valid round trips", async () => {
    const boundary = "0".repeat(63) + "1";
    const blob = await createSessionFile({ before: photo().photo, after: null, startingMass: boundary }, controller().signal);
    const restored = await restoreSessionFile(new File([blob], `saved${SESSION_FILE_ACCEPT}`), controller().signal);
    expect(restored.startingMass).toBe(boundary);
    releaseRestoredSession(restored);
    await expect(createSessionFile({ before: photo().photo, after: null, startingMass: "0" + boundary }, controller().signal)).rejects.toMatchObject({ code: "invalid" });
  });
  it("returns independent pixel copies and invalidates every owned accessor on release", async () => {
    const restored = await read(fixture(false));
    const first = restored.before.copyPixels(); first.data.fill(0);
    expect(hash(restored.before.copyPixels().data)).toBe(hash(pixels()));
    restored.before.release(); restored.before.release();
    expect(revokeUrl).toHaveBeenCalledOnce();
    expect(() => restored.before.copyPixels()).toThrow(SessionError);
    expect(() => restored.before.copyPreviewBlob!()).toThrow(SessionError);
  });
  it("deduplicates release when callers present the same photo twice", () => {
    const owned = photo().photo;
    releaseRestoredSession({ before: owned, after: owned, startingMass: "" });
    expect(owned.release).toHaveBeenCalledOnce();
  });
  it("does not authenticate photos: an intentionally recomputed checksum is accepted", async () => {
    const document = fixture(false);
    document.before.cropRgbaBase64 = b64(pixels(101));
    const restored = await read(document);
    expect(hash(restored.before.copyPixels().data)).toBe(hash(pixels(101)));
    releaseRestoredSession(restored);
  });
  it("preserves JPEG metadata bytes without claiming to strip them", async () => {
    const original = jpeg();
    const withComment = new Uint8Array([...original.subarray(0, 2), 0xff, 0xfe, 0, 5, 65, 66, 67, ...original.subarray(2)]);
    const document = fixture(false); document.before.previewJpegBase64 = b64(withComment);
    bitmap.mockResolvedValueOnce({ width: 640, height: 480, close: vi.fn() });
    const restored = await read(document);
    expect(new Uint8Array(await restored.before.copyPreviewBlob!().arrayBuffer())).toEqual(withComment);
    releaseRestoredSession(restored);
  });
  it("exposes an immutable captured-preview copy only while the camera photo is owned", async () => {
    const video = document.createElement("video");
    Object.defineProperties(video, {
      readyState: { value: 2 }, videoWidth: { value: 640 }, videoHeight: { value: 480 },
      srcObject: { value: { getVideoTracks: () => [{ readyState: "live", enabled: true, muted: false }] } },
    });
    const context = { drawImage: vi.fn(), getImageData: () => ({ data: new Uint8ClampedArray(640 * 480 * 4).fill(255) }) };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
    const blob = new Blob([jpeg()], { type: "image/jpeg" });
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => { callback(blob); });
    const captured = await captureFrame(video, controller().signal);
    const copy = captured.copyPreviewBlob!();
    expect(copy).not.toBe(blob); expect(await copy.arrayBuffer()).toEqual(await blob.arrayBuffer());
    const exported = await createSessionFile({ before: captured, after: null, startingMass: "" }, controller().signal);
    expect(exported.type).toBe("application/json");
    captured.release();
    expect(() => captured.copyPreviewBlob!()).toThrow(); expect(() => captured.copyPixels()).toThrow();
    expect(revokeUrl).toHaveBeenCalledOnce();
  });
});

describe("session schema, compatibility, mass and corruption gates", () => {
  it.each([null, [], {}, "https://example.test/image", 1].map((value) => ({ value })))("rejects a non-session root $value", async ({ value }) => {
    await expect(restoreSessionFile(file(value), controller().signal)).rejects.toMatchObject({ code: "invalid" });
    expect(bitmap).not.toHaveBeenCalled();
  });
  it("rejects unknown keys at every schema level", async () => {
    for (const level of ["root", "compatibility", "before"]) {
      const document = fixture();
      const target = level === "root" ? document : level === "compatibility" ? document.compatibility : document.before;
      Object.assign(target, { unexpected: "not allowed" });
      await expect(read(document)).rejects.toMatchObject({ code: "invalid" });
    }
    expect(bitmap).not.toHaveBeenCalled();
  });
  it.each([2, "1", null, -1])("rejects unsupported version %j", async (version) => {
    const document = { ...fixture(), version };
    await expect(restoreSessionFile(file(document), controller().signal)).rejects.toMatchObject({ code: "incompatible" });
  });
  it.each(["preprocessing", "modelVersion", "modelSha256"])("rejects changed %s compatibility", async (key) => {
    const document = fixture(); document.compatibility[key] = "different";
    await expect(read(document)).rejects.toMatchObject({ code: "incompatible" });
    expect(bitmap).not.toHaveBeenCalled();
  });
  it("requires before, exact nullable-after structure, string fields and fixed format", async () => {
    for (const mutation of [{ before: null }, { after: [] }, { before: { ...fixture().before, width: "640" } }]) {
      await expect(restoreSessionFile(file({ ...fixture(), ...mutation }), controller().signal)).rejects.toMatchObject({ code: "invalid" });
    }
    await expect(restoreSessionFile(file({ ...fixture(), format: "other" }), controller().signal)).rejects.toMatchObject({ code: "incompatible" });
  });
  it.each(["0", "-1", "NaN", "Infinity", "100001", "1e3", "0x10", " ", "3 ", "1".repeat(65), null, 200])("rejects invalid serialized mass %j", async (startingMass) => {
    await expect(restoreSessionFile(file({ ...fixture(), startingMass }), controller().signal)).rejects.toMatchObject({ code: "invalid" });
  });
  it.each([".5", "0001.20", "100000", "1."])("accepts valid bounded decimal mass %s", async (startingMass) => {
    const document = fixture(false); document.startingMass = startingMass;
    const restored = await read(document); expect(restored.startingMass).toBe(startingMass); releaseRestoredSession(restored);
  });
  it("rejects valid-looking but changed bytes when the checksum was not updated", async () => {
    const document = fixture(false); document.before.cropRgbaBase64 = b64(pixels(6));
    await expect(restoreSessionFile(file(document), controller().signal)).rejects.toMatchObject({ code: "corrupt" });
    expect(bitmap).not.toHaveBeenCalled();
  });
  it.each(["", "0".repeat(63), "A".repeat(64), null, 5])("rejects malformed checksum %j", async (checksum) => {
    await expect(restoreSessionFile(file({ ...fixture(), checksum }), controller().signal)).rejects.toMatchObject({ code: "invalid" });
  });
  it.each(["", "data:image/jpeg;base64,AAAA", "https://example.test/x", "AAAA\n", "AAA", "AA=A", "AB=="])("rejects noncanonical JPEG base64 %j before decoding", async (value) => {
    const document = fixture(); document.before.previewJpegBase64 = value;
    await expect(read(document)).rejects.toMatchObject({ code: "invalid" }); expect(bitmap).not.toHaveBeenCalled();
  });
  it("rejects short, oversized and noncanonical crop encodings", async () => {
    for (const encoded of ["AAAA", b64(new Uint8Array(224 * 224 * 4 + 1)), `${fixture().before.cropRgbaBase64.slice(0, -3)}B==`]) {
      const document = fixture(); document.before.cropRgbaBase64 = encoded;
      await expect(read(document)).rejects.toMatchObject({ code: "invalid" });
    }
    expect(bitmap).not.toHaveBeenCalled();
  });
  it("rejects nonopaque crop data even with a recomputed checksum", async () => {
    const crop = pixels(); crop[3] = 0;
    const document = fixture(false); document.before.cropRgbaBase64 = b64(crop);
    await expect(read(document)).rejects.toMatchObject({ code: "invalid" }); expect(bitmap).not.toHaveBeenCalled();
  });
});

describe("bounded local file and JPEG validation", () => {
  it.each([["session.json", "application/json"], ["photo.plategauge.json", "image/svg+xml"]])("rejects suffix/MIME %s %s", async (name, type) => {
    const input = file(fixture(), name, type); const readFile = vi.spyOn(input, "arrayBuffer");
    await expect(restoreSessionFile(input, controller().signal)).rejects.toMatchObject({ code: "invalid" }); expect(readFile).not.toHaveBeenCalled();
  });
  it("rejects empty and oversized files before reading, without reflecting their names", async () => {
    const empty = new File([], "private-person-name.plategauge.json");
    await expect(restoreSessionFile(empty, controller().signal)).rejects.toMatchObject({ code: "invalid" });
    const oversized = file(); Object.defineProperty(oversized, "size", { value: SESSION_MAX_BYTES + 1 });
    const readFile = vi.spyOn(oversized, "arrayBuffer");
    await expect(restoreSessionFile(oversized, controller().signal)).rejects.toMatchObject({ code: "too_large" }); expect(readFile).not.toHaveBeenCalled();
    expect(sessionErrorMessage(new Error(empty.name))).not.toContain("private-person");
  });
  it("rejects invalid JSON, invalid UTF-8, and a non-File object", async () => {
    for (const bytes of [new TextEncoder().encode("{ broken JSON"), new Uint8Array([0xc3, 0x28])]) {
      await expect(restoreSessionFile(new File([bytes], "x.plategauge.json"), controller().signal)).rejects.toMatchObject({ code: "invalid" });
    }
    await expect(restoreSessionFile({ size: 1 } as File, controller().signal)).rejects.toMatchObject({ code: "invalid" });
  });
  it.each([[223, 480], [640, 0], [1281, 480], [640, 480.5], [1e9, 1e9]])("rejects dimensions %s × %s before decode", async (width, height) => {
    const document = fixture(); Object.assign(document.before, { width, height });
    await expect(read(document)).rejects.toMatchObject({ code: "invalid" }); expect(bitmap).not.toHaveBeenCalled();
  });
  it.each(["magic", "end", "dimensions", "components", "precision", "length", "no-frame", "duplicate-frame", "marker"])("rejects JPEG %s corruption before native decoding", async (change) => {
    let bytes = jpeg();
    if (change === "magic") bytes[0] = 0;
    if (change === "end") bytes[bytes.length - 1] = 0;
    if (change === "dimensions") bytes[10] = 1;
    if (change === "components") bytes[11] = 4;
    if (change === "precision") bytes[6] = 12;
    if (change === "length") bytes[5] = 255;
    if (change === "no-frame") bytes = new Uint8Array([...bytes.subarray(0, 2), ...bytes.subarray(21)]);
    if (change === "duplicate-frame") bytes = new Uint8Array([...bytes.subarray(0, 21), ...bytes.subarray(2, 21), ...bytes.subarray(21)]);
    if (change === "marker") bytes[3] = 0;
    const document = fixture(false); document.before.previewJpegBase64 = b64(bytes);
    await expect(read(document)).rejects.toMatchObject({ code: "invalid" }); expect(bitmap).not.toHaveBeenCalled();
  });
  it("rejects decoded dimensions inconsistent with the bounded JPEG header and closes the bitmap", async () => {
    const close = vi.fn(); bitmap.mockResolvedValueOnce({ width: 9000, height: 9000, close });
    await expect(read(fixture(false))).rejects.toMatchObject({ code: "invalid" }); expect(close).toHaveBeenCalledOnce(); expect(createUrl).not.toHaveBeenCalled();
  });
  it("rejects a second frame header after a scan before native decoding", async () => {
    const original = jpeg();
    const bytes = new Uint8Array([...original.subarray(0, -2), ...original.subarray(2)]);
    const document = fixture(false); document.before.previewJpegBase64 = b64(bytes);
    await expect(read(document)).rejects.toMatchObject({ code: "invalid" }); expect(bitmap).not.toHaveBeenCalled();
  });
  it("accepts escaped entropy bytes and restart markers without misreading them as frame headers", async () => {
    const original = jpeg();
    const bytes = new Uint8Array([...original.subarray(0, -2), 0xff, 0, 0xc0, 0xff, 0xd0, 0, 0xff, 0xd9]);
    const document = fixture(false); document.before.previewJpegBase64 = b64(bytes);
    const restored = await read(document); releaseRestoredSession(restored);
  });
  it("sanitizes native decoder failures and fails closed when decoding or crypto is unavailable", async () => {
    bitmap.mockRejectedValueOnce(new Error("secret path and pixels"));
    await read(fixture(false)).catch((error: unknown) => expect(sessionErrorMessage(error)).not.toContain("secret"));
    vi.stubGlobal("createImageBitmap", undefined);
    await expect(read(fixture(false))).rejects.toMatchObject({ code: "unsupported" });
    vi.stubGlobal("crypto", undefined);
    await expect(read(fixture(false))).rejects.toMatchObject({ code: "unsupported" });
  });
  it("releases the already restored before photo if the after decoder fails", async () => {
    bitmap.mockRejectedValueOnce(new Error("private decoder error"));
    await expect(read(fixture())).rejects.toMatchObject({ code: "invalid" }); expect(createUrl).not.toHaveBeenCalled();
    bitmap.mockResolvedValueOnce({ width: 640, height: 480, close: vi.fn() })
      .mockRejectedValueOnce(new Error("after decoder failed"));
    await expect(read(fixture())).rejects.toMatchObject({ code: "invalid" });
    expect(createUrl).toHaveBeenCalledOnce(); expect(revokeUrl).toHaveBeenCalledExactlyOnceWith("blob:synthetic-session-1");
  });
});

describe("export validation and cancellation ownership", () => {
  it("rejects unexportable photos, invalid crops, invalid mass and invalid preview types", async () => {
    const missing = { ...photo().photo, copyPreviewBlob: undefined };
    await expect(createSessionFile({ before: missing, after: null, startingMass: "" }, controller().signal)).rejects.toMatchObject({ code: "unsupported" });
    const bad = photo(); const data = pixels(); data[3] = 0;
    vi.mocked(bad.photo.copyPixels).mockReturnValueOnce({ width: 224, height: 224, data });
    await expect(createSessionFile({ before: bad.photo, after: null, startingMass: "" }, controller().signal)).rejects.toMatchObject({ code: "invalid" }); expect(data.every((value) => value === 0)).toBe(true);
    await expect(createSessionFile({ before: photo().photo, after: null, startingMass: "-1" }, controller().signal)).rejects.toMatchObject({ code: "invalid" });
    for (const blob of [new Blob([], { type: "image/jpeg" }), new Blob(["svg"], { type: "image/svg+xml" })]) {
      const value = photo(); vi.mocked(value.photo.copyPreviewBlob).mockReturnValueOnce(blob);
      await expect(createSessionFile({ before: value.photo, after: null, startingMass: "" }, controller().signal)).rejects.toMatchObject({ code: "invalid" });
      expect(value.copies[0]!.every((byte) => byte === 0)).toBe(true);
    }
  });
  it("rejects a preview over 5 MiB before reading it", async () => {
    const value = photo(); const blob = new Blob(["fake"], { type: "image/jpeg" });
    Object.defineProperty(blob, "size", { value: 5 * 1024 * 1024 + 1 });
    const readBlob = vi.spyOn(blob, "arrayBuffer"); vi.mocked(value.photo.copyPreviewBlob).mockReturnValueOnce(blob);
    await expect(createSessionFile({ before: value.photo, after: null, startingMass: "" }, controller().signal)).rejects.toMatchObject({ code: "too_large" });
    expect(readBlob).not.toHaveBeenCalled(); expect(value.copies[0]!.every((byte) => byte === 0)).toBe(true);
  });
  it("does no work when cancelled before export or restore", async () => {
    const abort = controller(); abort.abort(); const owned = photo(); const input = file(); const readFile = vi.spyOn(input, "arrayBuffer");
    await expect(createSessionFile({ before: owned.photo, after: null, startingMass: "" }, abort.signal)).rejects.toMatchObject({ code: "cancelled" });
    await expect(restoreSessionFile(input, abort.signal)).rejects.toMatchObject({ code: "cancelled" });
    expect(owned.photo.copyPixels).not.toHaveBeenCalled(); expect(readFile).not.toHaveBeenCalled();
  });
  it("wipes a late file read after cancellation", async () => {
    const input = file(); const abort = controller(); let finish!: (buffer: ArrayBuffer) => void;
    vi.spyOn(input, "arrayBuffer").mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const pending = restoreSessionFile(input, abort.signal); const failure = expect(pending).rejects.toMatchObject({ code: "cancelled" });
    abort.abort(); await failure;
    const late = new Uint8Array([5, 6, 7]); finish(late.buffer); await Promise.resolve(); await Promise.resolve();
    expect([...late]).toEqual([0, 0, 0]); expect(bitmap).not.toHaveBeenCalled();
  });
  it("bounds a stuck file read and wipes its eventual result", async () => {
    vi.useFakeTimers(); const input = file(); let finish!: (buffer: ArrayBuffer) => void;
    vi.spyOn(input, "arrayBuffer").mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const pending = restoreSessionFile(input, controller().signal); const failure = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(LOCAL_OPERATION_TIMEOUT_MS); await failure;
    const late = new Uint8Array([8]); finish(late.buffer); await Promise.resolve(); await Promise.resolve();
    expect(late[0]).toBe(0); expect(vi.getTimerCount()).toBe(0);
  });
  it("closes a late decoder result after cancellation without creating a preview URL", async () => {
    const abort = controller(); let finish!: (bitmap: ImageBitmap) => void;
    bitmap.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const pending = restoreSessionFile(file(fixture(false)), abort.signal);
    const failure = expect(pending).rejects.toMatchObject({ code: "cancelled" });
    await vi.waitFor(() => expect(bitmap).toHaveBeenCalledOnce()); abort.abort(); await failure;
    const close = vi.fn(); finish({ width: 640, height: 480, close });
    await Promise.resolve(); await Promise.resolve();
    expect(close).toHaveBeenCalledOnce(); expect(createUrl).not.toHaveBeenCalled();
  });
  it("revokes partial URLs if cancellation occurs during pair construction", async () => {
    const abort = controller();
    createUrl.mockImplementation(() => { if (createUrl.mock.calls.length === 2) abort.abort(); return `blob:partial-${createUrl.mock.calls.length}`; });
    await expect(restoreSessionFile(file(), abort.signal)).rejects.toMatchObject({ code: "cancelled" });
    expect(revokeUrl.mock.calls.flat().sort()).toEqual(["blob:partial-1", "blob:partial-2"]);
  });
  it("wipes export copies if preparation is cancelled while JPEG decode is pending", async () => {
    const owned = photo(); const abort = controller(); let finish!: (bitmap: ImageBitmap) => void;
    bitmap.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const pending = createSessionFile({ before: owned.photo, after: null, startingMass: "" }, abort.signal);
    const failure = expect(pending).rejects.toMatchObject({ code: "cancelled" });
    await vi.waitFor(() => expect(bitmap).toHaveBeenCalledOnce()); abort.abort(); await failure;
    expect(owned.copies[0]!.every((value) => value === 0)).toBe(true); expect(owned.photo.release).not.toHaveBeenCalled();
    const close = vi.fn(); finish({ width: 640, height: 480, close });
    await Promise.resolve(); await Promise.resolve(); expect(close).toHaveBeenCalledOnce();
  });
});
