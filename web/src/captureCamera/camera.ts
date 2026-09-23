import { boundedOperation, LocalOperationError } from "../capturePrototype/operations";
import { preparePillowCrop, type OpaqueRgbaImage } from "../libv2/pillowResize";

export type CameraFacing = "environment" | "user";
export interface CameraPhoto {
  readonly url: string;
  readonly width: number;
  readonly height: number;
  /** Copy of the original frame's 224px model crop, not decoded JPEG preview pixels. */
  copyPixels(): OpaqueRgbaImage;
  /** Immutable local JPEG preview for an explicitly requested session export. */
  copyPreviewBlob?(): Blob;
  release(): void;
}

export type CameraErrorCode =
  | "insecure_context"
  | "camera_unavailable"
  | "permission_denied"
  | "camera_missing"
  | "camera_busy"
  | "security_restriction"
  | "unsupported_constraints"
  | "cancelled"
  | "timeout"
  | "frame_not_ready"
  | "invalid_frame"
  | "frame_too_large"
  | "encoding_failed"
  | "photo_too_large";

const MESSAGES: Record<CameraErrorCode, string> = {
  insecure_context: "Camera access requires a secure HTTPS page or a supported localhost preview.",
  camera_unavailable: "This browser cannot provide camera access. Try a supported browser with a camera.",
  permission_denied: "Camera access was not granted. Check browser/device permissions, or open this page directly in your browser.",
  camera_missing: "No usable camera was found. Connect or enable a camera and try again.",
  camera_busy: "The camera could not start. It may be in use by another application; close that application and try again.",
  security_restriction: "The browser or page security policy blocked camera access. Open the preview directly in a supported browser.",
  unsupported_constraints: "The camera could not provide the requested capture settings. Try another camera.",
  cancelled: "Camera preparation was cancelled. No photo was saved.",
  timeout: "The camera operation took too long. Close any permission prompt, then try again when you are ready.",
  frame_not_ready: "The camera is still preparing a frame. Wait for the live preview before taking a photo.",
  invalid_frame: "The camera frame is invalid or smaller than 224 pixels on either side. Try another camera.",
  frame_too_large: "The camera frame exceeds the 16-megapixel processing limit. Try a lower-resolution camera setting.",
  encoding_failed: "The photo could not be prepared in this browser. Try taking it again.",
  photo_too_large: "The captured photo exceeds the 5 MB limit. Try taking it again.",
};

export class CameraError extends Error {
  constructor(readonly code: CameraErrorCode) {
    super(MESSAGES[code]);
    this.name = "CameraError";
  }
}

export const CAMERA_LIMITS = Object.freeze({
  maximumSourcePixels: 16_000_000,
  minimumSourceSide: 224,
  maximumCaptureSide: 1280,
  maximumPhotoBytes: 5 * 1024 * 1024,
  jpegQuality: 0.9,
});

function abortIfRequested(signal: AbortSignal): void {
  if (signal.aborted) throw new CameraError("cancelled");
}

function requireLiveVideoSource(video: HTMLVideoElement): void {
  const source = video.srcObject;
  try {
    if (!source || !("getVideoTracks" in source) || typeof source.getVideoTracks !== "function"
      || !source.getVideoTracks().some((track) => track.readyState === "live" && track.enabled === true && track.muted === false)) {
      throw new CameraError("frame_not_ready");
    }
  } catch {
    throw new CameraError("frame_not_ready");
  }
}

function normalizeCameraError(error: unknown): CameraError {
  if (error instanceof CameraError) return error;
  if (error instanceof LocalOperationError) return new CameraError(error.code);
  const name = error instanceof Error || error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") return new CameraError("permission_denied");
  if (name === "NotFoundError" || name === "DevicesNotFoundError") return new CameraError("camera_missing");
  if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError") return new CameraError("camera_busy");
  if (name === "SecurityError") return new CameraError("security_restriction");
  if (name === "OverconstrainedError" || name === "ConstraintNotSatisfiedError") return new CameraError("unsupported_constraints");
  return new CameraError("camera_unavailable");
}

/** Never echo browser/device error details, which may contain identifying information. */
export function cameraErrorMessage(error: unknown): string {
  return normalizeCameraError(error).message;
}

/** The caller also owns clearing video.srcObject when leaving or switching cameras. */
export function stopStream(stream: MediaStream): void {
  let tracks: MediaStreamTrack[];
  try { tracks = stream.getTracks(); }
  catch { return; }
  for (const track of tracks) {
    // Attempt every track even if a faulty implementation throws for one of them.
    try { track.stop(); }
    catch { /* Cleanup is best-effort; no device details are logged. */ }
  }
}

/**
 * Call only from an explicit camera-button action, never on render or page load.
 * No device enumeration/audio request; unresolved permission has a 15s acceptance
 * deadline. Browser permission prompts cannot be programmatically dismissed, so
 * any stream granted after timeout/cancellation is immediately stopped.
 */
export async function requestCamera(signal: AbortSignal, facing: CameraFacing = "environment"): Promise<MediaStream> {
  abortIfRequested(signal);
  if (!globalThis.isSecureContext) throw new CameraError("insecure_context");
  if (facing !== "environment" && facing !== "user") throw new CameraError("unsupported_constraints");
  const media = navigator.mediaDevices;
  if (!media || typeof media.getUserMedia !== "function") throw new CameraError("camera_unavailable");
  let stream: MediaStream | undefined;
  try {
    stream = await boundedOperation(async () => {
      try {
        return await media.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: facing },
            width: { ideal: 1280, max: 1280 },
            height: { ideal: 960, max: 960 },
          },
        });
      } catch (error) {
        // Normalize native DOMExceptions before the general operation wrapper;
        // they are not Error subclasses in every runtime or test realm.
        throw normalizeCameraError(error);
      }
    }, signal, stopStream);
    abortIfRequested(signal);
    if (!stream.getVideoTracks().some((track) => track.readyState === "live") || stream.getAudioTracks().length > 0) {
      throw new CameraError("camera_missing");
    }
    return stream;
  } catch (error) {
    if (stream) stopStream(stream);
    throw normalizeCameraError(error);
  }
}

/**
 * Snapshot original-frame sRGB pixels once. Prepare the versioned Pillow crop
 * before preview resizing/JPEG encoding, then discard source pixels. Retains a
 * temporary visual-preview URL and a 224px crop only. No inference/network/storage.
 */
export async function captureFrame(video: HTMLVideoElement, signal: AbortSignal): Promise<CameraPhoto> {
  abortIfRequested(signal);
  if (!Number.isInteger(video.readyState) || video.readyState < 2 || video.readyState > 4 || video.error) throw new CameraError("frame_not_ready");
  // readyState may retain a cached frame after a stream stops or becomes muted.
  requireLiveVideoSource(video);
  const sourceWidth = video.videoWidth;
  const sourceHeight = video.videoHeight;
  if (![sourceWidth, sourceHeight].every((side) => Number.isSafeInteger(side) && side >= CAMERA_LIMITS.minimumSourceSide)) {
    throw new CameraError("invalid_frame");
  }
  if (sourceWidth * sourceHeight > CAMERA_LIMITS.maximumSourcePixels) throw new CameraError("frame_too_large");
  const scale = Math.min(1, CAMERA_LIMITS.maximumCaptureSide / Math.max(sourceWidth, sourceHeight));
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));
  if (Math.min(width, height) < 224) throw new CameraError("invalid_frame");
  let canvas: HTMLCanvasElement | undefined;
  let previewCanvas: HTMLCanvasElement | undefined;
  let sourcePixels: Uint8ClampedArray | undefined;
  let modelPixels: OpaqueRgbaImage | undefined;
  let createdUrl: string | undefined;
  let returned = false;
  try {
    canvas = document.createElement("canvas");
    canvas.width = sourceWidth; canvas.height = sourceHeight;
    const context = canvas.getContext("2d", { alpha: false, colorSpace: "srgb" });
    if (!context) throw new CameraError("encoding_failed");
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.drawImage(video, 0, 0, sourceWidth, sourceHeight);
    sourcePixels = context.getImageData(0, 0, sourceWidth, sourceHeight).data;
    const preprocessing = new AbortController();
    const stopPreprocessing = () => preprocessing.abort();
    signal.addEventListener("abort", stopPreprocessing, { once: true });
    try {
      const originalFrame = { width: sourceWidth, height: sourceHeight, data: sourcePixels };
      modelPixels = await boundedOperation(
        () => preparePillowCrop(originalFrame, { signal: preprocessing.signal }),
        signal,
        (late) => late.data.fill(0),
      );
    } finally {
      preprocessing.abort();
      signal.removeEventListener("abort", stopPreprocessing);
    }
    sourcePixels.fill(0); sourcePixels = undefined;
    abortIfRequested(signal);
    previewCanvas = document.createElement("canvas");
    previewCanvas.width = width; previewCanvas.height = height;
    const previewContext = previewCanvas.getContext("2d", { alpha: false, colorSpace: "srgb" });
    if (!previewContext) throw new CameraError("encoding_failed");
    previewContext.imageSmoothingEnabled = true;
    previewContext.imageSmoothingQuality = "high";
    previewContext.drawImage(canvas, 0, 0, width, height);
    canvas.width = 0; canvas.height = 0;
    const canvasToEncode = previewCanvas;
    const blob = await boundedOperation(() => new Promise<Blob>((resolve, reject) => {
      canvasToEncode.toBlob((value) => value ? resolve(value) : reject(new CameraError("encoding_failed")), "image/jpeg", CAMERA_LIMITS.jpegQuality);
    }), signal, () => undefined);
    abortIfRequested(signal);
    if (blob.type !== "image/jpeg" || blob.size === 0) throw new CameraError("encoding_failed");
    if (blob.size > CAMERA_LIMITS.maximumPhotoBytes) throw new CameraError("photo_too_large");
    const url = URL.createObjectURL(blob);
    createdUrl = url;
    abortIfRequested(signal);
    let released = false;
    const retainedPixels = modelPixels;
    let retainedPreview: Blob | null = blob;
    const photo: CameraPhoto = {
      url, width, height,
      copyPixels: () => {
        if (released) throw new CameraError("invalid_frame");
        return { width: 224, height: 224, data: new Uint8ClampedArray(retainedPixels.data) };
      },
      copyPreviewBlob: () => {
        if (released || !retainedPreview) throw new CameraError("invalid_frame");
        return retainedPreview.slice(0, retainedPreview.size, "image/jpeg");
      },
      release: () => {
        if (released) return;
        released = true;
        retainedPixels.data.fill(0);
        retainedPreview = null;
        URL.revokeObjectURL(url);
      },
    };
    returned = true;
    return photo;
  } catch (error) {
    if (signal.aborted) throw new CameraError("cancelled");
    if (error instanceof CameraError || error instanceof LocalOperationError) throw normalizeCameraError(error);
    throw new CameraError("encoding_failed");
  } finally {
    if (createdUrl && !returned) URL.revokeObjectURL(createdUrl);
    sourcePixels?.fill(0);
    if (!returned) modelPixels?.data.fill(0);
    if (canvas) { canvas.width = 0; canvas.height = 0; }
    if (previewCanvas) { previewCanvas.width = 0; previewCanvas.height = 0; }
  }
}
