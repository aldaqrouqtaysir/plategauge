import { boundedOperation, LocalOperationError, wipeBuffer } from "../capturePrototype/operations";
import { EXPERIMENTAL_MODEL, validModelPixels } from "../experimentalEstimator/contract";
import { CAMERA_LIMITS, type CameraPhoto } from "./camera";
import { parseStartingMass } from "./startingMass";

/**
 * Explicit, unencrypted local files only; no estimate or device/timestamp schema fields.
 * JPEG bytes are preserved, not metadata-sanitized. Checksums detect corruption only:
 * a recomputed checksum does not prove capture provenance or crop/preview agreement.
 */
export const SESSION_FILE_ACCEPT = ".plategauge.json";
export const SESSION_MAX_BYTES = 15 * 1024 * 1024;
export const SESSION_COMPATIBILITY = Object.freeze({
  preprocessing: "original-frame-pillow-bicubic-short256-center224-r1",
  modelVersion: EXPERIMENTAL_MODEL.version,
  modelSha256: EXPERIMENTAL_MODEL.sha256,
});
const CROP_BYTES = 224 * 224 * 4;
const MIME = "application/json";

export interface RestoredSession {
  before: CameraPhoto;
  after: CameraPhoto | null;
  startingMass: string;
}

interface EncodedPhoto {
  width: number;
  height: number;
  previewJpegBase64: string;
  cropRgbaBase64: string;
}
interface SessionPayload {
  format: "plategauge-session";
  version: 1;
  compatibility: typeof SESSION_COMPATIBILITY;
  before: EncodedPhoto;
  after: EncodedPhoto | null;
  startingMass: string;
}
type SessionErrorCode = "invalid" | "incompatible" | "corrupt" | "too_large" | "cancelled" | "timeout" | "unsupported";
const MESSAGES: Record<SessionErrorCode, string> = {
  invalid: "This session file is not valid. Choose a supported PlateGauge session file.",
  incompatible: "This session uses an unsupported version or a different model/preprocessing format.",
  corrupt: "This session did not pass its corruption check. Choose the original saved file.",
  too_large: "The session exceeds the 15 MiB file or supported photo limits.",
  cancelled: "Session preparation was cancelled. No session was replaced.",
  timeout: "Session preparation took too long. Try again or choose another file.",
  unsupported: "This browser could not prepare the session file. Try a supported browser.",
};
export class SessionError extends Error {
  constructor(readonly code: SessionErrorCode) { super(MESSAGES[code]); this.name = "SessionError"; }
}
function normalize(error: unknown): SessionError {
  if (error instanceof SessionError) return error;
  if (error instanceof LocalOperationError) return new SessionError(error.code);
  return new SessionError("invalid");
}
/** Never reflect file names, JSON, URLs, native decoder errors, or photo contents. */
export function sessionErrorMessage(error: unknown): string { return normalize(error).message; }
function checkAbort(signal: AbortSignal): void { if (signal.aborted) throw new SessionError("cancelled"); }

function record(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) throw new SessionError("invalid");
  const object = value as Record<string, unknown>;
  const actual = Object.keys(object);
  if (actual.length !== keys.length || actual.some((key) => !keys.includes(key))) throw new SessionError("invalid");
  return object;
}
function mass(value: unknown): string {
  if (typeof value !== "string") throw new SessionError("invalid");
  const parsed = parseStartingMass(value);
  if (parsed.error) throw new SessionError("invalid");
  return parsed.text;
}
function dimensions(width: unknown, height: unknown): asserts width is number {
  if (typeof width !== "number" || typeof height !== "number"
    || !Number.isSafeInteger(width) || !Number.isSafeInteger(height)
    || Math.min(width, height) < 224 || Math.max(width, height) > CAMERA_LIMITS.maximumCaptureSide) {
    throw new SessionError("invalid");
  }
}
function base64(bytes: Uint8Array | Uint8ClampedArray): string {
  const chunks: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 16_384) {
    chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 16_384)));
  }
  return btoa(chunks.join(""));
}
function checkedBase64(value: unknown, maximumBytes: number, exact = false): string {
  if (typeof value !== "string" || value.length === 0 || value.length % 4 !== 0
    || value.length > 4 * Math.ceil(maximumBytes / 3)) throw new SessionError("invalid");
  let padding = 0;
  if (value.endsWith("==")) padding = 2;
  else if (value.endsWith("=")) padding = 1;
  const size = value.length / 4 * 3 - padding;
  if (size < 1 || size > maximumBytes || (exact && size !== maximumBytes)) throw new SessionError("invalid");
  for (let index = 0; index < value.length - padding; index += 1) {
    const code = value.charCodeAt(index);
    if (!((code >= 65 && code <= 90) || (code >= 97 && code <= 122)
      || (code >= 48 && code <= 57) || code === 43 || code === 47)) throw new SessionError("invalid");
  }
  // Canonical unused padding bits: strings that decode alike must not have two encodings.
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const last = alphabet.indexOf(value[value.length - padding - 1]!);
  if ((padding === 2 && last % 16 !== 0) || (padding === 1 && last % 4 !== 0)) throw new SessionError("invalid");
  return value;
}
function decode(value: string): Uint8Array<ArrayBuffer> {
  const binary = atob(value);
  const result = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) result[index] = binary.charCodeAt(index);
  return result;
}
function photoRecord(value: unknown): EncodedPhoto {
  const photo = record(value, ["width", "height", "previewJpegBase64", "cropRgbaBase64"]);
  dimensions(photo.width, photo.height);
  return {
    width: photo.width, height: photo.height as number,
    previewJpegBase64: checkedBase64(photo.previewJpegBase64, CAMERA_LIMITS.maximumPhotoBytes),
    cropRgbaBase64: checkedBase64(photo.cropRgbaBase64, CROP_BYTES, true),
  };
}
function payload(value: unknown): { content: SessionPayload; checksum: string } {
  const top = record(value, ["format", "version", "compatibility", "before", "after", "startingMass", "checksum"]);
  if (top.format !== "plategauge-session" || top.version !== 1) throw new SessionError("incompatible");
  const compatibility = record(top.compatibility, ["preprocessing", "modelVersion", "modelSha256"]);
  if (Object.entries(SESSION_COMPATIBILITY).some(([key, expected]) => compatibility[key] !== expected)) {
    throw new SessionError("incompatible");
  }
  if (typeof top.checksum !== "string" || !/^[a-f0-9]{64}$/.test(top.checksum)) throw new SessionError("invalid");
  const startingMass = mass(top.startingMass);
  if (startingMass !== top.startingMass) throw new SessionError("invalid");
  return {
    content: { format: "plategauge-session", version: 1, compatibility: SESSION_COMPATIBILITY,
      before: photoRecord(top.before), after: top.after === null ? null : photoRecord(top.after), startingMass },
    checksum: top.checksum,
  };
}
async function digest(content: SessionPayload, signal: AbortSignal): Promise<string> {
  checkAbort(signal);
  if (!globalThis.crypto?.subtle) throw new SessionError("unsupported");
  const bytes = new TextEncoder().encode(JSON.stringify(content));
  try {
    const hash = await boundedOperation(() => crypto.subtle.digest("SHA-256", bytes), signal, wipeBuffer);
    try { checkAbort(signal); return [...new Uint8Array(hash)].map((value) => value.toString(16).padStart(2, "0")).join(""); }
    finally { wipeBuffer(hash); }
  } finally { bytes.fill(0); }
}

/** Inspect dimensions before decoding to bound decoder allocation. Decoder still validates the JPEG. */
function checkJpeg(bytes: Uint8Array, width: number, height: number): void {
  if (bytes.length < 16 || bytes[0] !== 0xff || bytes[1] !== 0xd8
    || bytes[bytes.length - 2] !== 0xff || bytes[bytes.length - 1] !== 0xd9) throw new SessionError("invalid");
  let offset = 2;
  let foundFrame = false;
  let foundScan = false;
  while (offset < bytes.length) {
    if (bytes[offset++] !== 0xff) throw new SessionError("invalid");
    while (bytes[offset] === 0xff) offset += 1;
    const marker = bytes[offset++];
    if (marker === 0xd9 && offset === bytes.length && foundFrame && foundScan) return;
    if (marker === undefined || marker === 0 || marker === 0xd8 || marker === 0xd9 || marker === 0xdc) throw new SessionError("invalid");
    const length = (bytes[offset] ?? 0) * 256 + (bytes[offset + 1] ?? 0);
    if (length < 2 || offset + length > bytes.length - 2) throw new SessionError("invalid");
    if (marker === 0xda) {
      if (!foundFrame) throw new SessionError("invalid");
      foundScan = true;
      offset += length;
      // Walk entropy-coded bytes without decoding. Escaped FF and restart markers
      // are data; later structural markers must still pass the same bounded checks.
      while (offset < bytes.length) {
        if (bytes[offset] !== 0xff) { offset += 1; continue; }
        const start = offset;
        while (bytes[offset] === 0xff) offset += 1;
        const next = bytes[offset];
        if (next === 0 || (next !== undefined && next >= 0xd0 && next <= 0xd7)) { offset += 1; continue; }
        offset = start;
        break;
      }
      continue;
    }
    if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
      if (foundFrame || ![0xc0, 0xc1, 0xc2].includes(marker) || length !== 17
        || bytes[offset + 2] !== 8 || bytes[offset + 7] !== 3
        || (bytes[offset + 3]! * 256 + bytes[offset + 4]!) !== height
        || (bytes[offset + 5]! * 256 + bytes[offset + 6]!) !== width) throw new SessionError("invalid");
      foundFrame = true;
    }
    offset += length;
  }
  throw new SessionError("invalid");
}
async function validatePreview(blob: Blob, bytes: Uint8Array, width: number, height: number, signal: AbortSignal): Promise<void> {
  checkJpeg(bytes, width, height);
  checkAbort(signal);
  if (typeof createImageBitmap !== "function") throw new SessionError("unsupported");
  const bitmap = await boundedOperation(() => createImageBitmap(blob, { imageOrientation: "none" }), signal, (late) => late.close());
  try {
    checkAbort(signal);
    if (bitmap.width !== width || bitmap.height !== height) throw new SessionError("invalid");
  } finally { bitmap.close(); }
}

async function encodePhoto(photo: CameraPhoto, signal: AbortSignal): Promise<EncodedPhoto> {
  checkAbort(signal);
  const width = photo.width; const height = photo.height;
  dimensions(width, height);
  if (typeof photo.copyPreviewBlob !== "function") throw new SessionError("unsupported");
  const pixels = photo.copyPixels();
  let previewBytes: Uint8Array<ArrayBuffer> | undefined;
  try {
    if (!validModelPixels(pixels.width, pixels.height, pixels.data)) throw new SessionError("invalid");
    const preview = photo.copyPreviewBlob();
    if (!(preview instanceof Blob) || preview.type !== "image/jpeg" || preview.size === 0) throw new SessionError("invalid");
    if (preview.size > CAMERA_LIMITS.maximumPhotoBytes) throw new SessionError("too_large");
    previewBytes = new Uint8Array(await boundedOperation(() => preview.arrayBuffer(), signal, wipeBuffer));
    await validatePreview(preview, previewBytes, width, height, signal);
    checkAbort(signal);
    return { width, height, previewJpegBase64: base64(previewBytes), cropRgbaBase64: base64(pixels.data) };
  } finally { pixels.data.fill(0); previewBytes?.fill(0); }
}

/** No automatic persistence. Caller must offer this Blob through an explicit download action. */
export async function createSessionFile(session: RestoredSession, signal: AbortSignal): Promise<Blob> {
  try {
    checkAbort(signal);
    const startingMass = mass(session.startingMass);
    const before = session.before; const after = session.after;
    const content: SessionPayload = {
      format: "plategauge-session", version: 1, compatibility: SESSION_COMPATIBILITY,
      before: await encodePhoto(before, signal),
      after: after === null ? null : await encodePhoto(after, signal), startingMass,
    };
    const checksum = await digest(content, signal);
    const file = new Blob([JSON.stringify({ ...content, checksum })], { type: MIME });
    if (file.size > SESSION_MAX_BYTES) throw new SessionError("too_large");
    checkAbort(signal);
    return file;
  } catch (error) { throw normalize(error); }
}

async function restorePhoto(encoded: EncodedPhoto, signal: AbortSignal): Promise<CameraPhoto> {
  checkAbort(signal);
  const jpeg = decode(encoded.previewJpegBase64);
  const crop = new Uint8ClampedArray(decode(encoded.cropRgbaBase64).buffer);
  let owned = false;
  let url: string | undefined;
  try {
    if (!validModelPixels(224, 224, crop)) throw new SessionError("invalid");
    let preview: Blob | null = new Blob([jpeg], { type: "image/jpeg" });
    await validatePreview(preview, jpeg, encoded.width, encoded.height, signal);
    checkAbort(signal);
    url = URL.createObjectURL(preview);
    checkAbort(signal);
    const previewUrl = url;
    let released = false;
    const photo: CameraPhoto = {
      url: previewUrl, width: encoded.width, height: encoded.height,
      copyPixels: () => {
        if (released) throw new SessionError("invalid");
        return { width: 224, height: 224, data: new Uint8ClampedArray(crop) };
      },
      copyPreviewBlob: () => {
        if (released || !preview) throw new SessionError("invalid");
        return preview.slice(0, preview.size, "image/jpeg");
      },
      release: () => {
        if (released) return;
        released = true; crop.fill(0); preview = null;
        URL.revokeObjectURL(previewUrl);
      },
    };
    owned = true;
    return photo;
  } finally {
    jpeg.fill(0);
    if (!owned) { crop.fill(0); if (url) URL.revokeObjectURL(url); }
  }
}

/** Returned photos are caller-owned; failure/abort releases every partially restored photo. */
export async function restoreSessionFile(file: File, signal: AbortSignal): Promise<RestoredSession> {
  let before: CameraPhoto | undefined;
  let after: CameraPhoto | null = null;
  let returned = false;
  try {
    checkAbort(signal);
    if (!(file instanceof File) || !file.name.toLowerCase().endsWith(SESSION_FILE_ACCEPT)
      || (file.type !== "" && file.type !== MIME) || file.size === 0) throw new SessionError("invalid");
    if (file.size > SESSION_MAX_BYTES) throw new SessionError("too_large");
    const bytes = await boundedOperation(() => file.arrayBuffer(), signal, wipeBuffer);
    let envelope: unknown;
    try {
      checkAbort(signal);
      envelope = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)) as unknown;
    } finally { wipeBuffer(bytes); }
    const parsed = payload(envelope);
    if (await digest(parsed.content, signal) !== parsed.checksum) throw new SessionError("corrupt");
    before = await restorePhoto(parsed.content.before, signal);
    after = parsed.content.after === null ? null : await restorePhoto(parsed.content.after, signal);
    checkAbort(signal);
    returned = true;
    return { before, after, startingMass: parsed.content.startingMass };
  } catch (error) { throw normalize(error); }
  finally { if (!returned) { before?.release(); after?.release(); } }
}

/** Best-effort cleanup cannot erase immutable strings/Blobs, downloaded files, or browser copies. */
export function releaseRestoredSession(session: RestoredSession): void {
  for (const photo of new Set([session.before, session.after])) photo?.release();
}
