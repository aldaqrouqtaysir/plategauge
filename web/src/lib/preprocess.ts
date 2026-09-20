import type { InspectedImage, PreparedImage } from "../types";

const RESIZE_SHORT_EDGE = 256;
const CROP_SIZE = 224;

export interface PreprocessGeometry {
  resizedWidth: number;
  resizedHeight: number;
  cropLeft: number;
  cropTop: number;
}

function roundHalfToEven(value: number): number {
  const lower = Math.floor(value);
  const fraction = value - lower;
  if (fraction < 0.5) return lower;
  if (fraction > 0.5) return lower + 1;
  return lower % 2 === 0 ? lower : lower + 1;
}

/** Mirrors Python/Pillow's rounded integer resize dimensions and integer center-crop offsets. */
export function calculatePreprocessGeometry(width: number, height: number): PreprocessGeometry {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0) {
    throw new Error("Image dimensions must be positive integers.");
  }
  const scale = RESIZE_SHORT_EDGE / Math.min(width, height);
  const resizedWidth = Math.max(RESIZE_SHORT_EDGE, roundHalfToEven(width * scale));
  const resizedHeight = Math.max(RESIZE_SHORT_EDGE, roundHalfToEven(height * scale));
  return {
    resizedWidth,
    resizedHeight,
    cropLeft: Math.floor((resizedWidth - CROP_SIZE) / 2),
    cropTop: Math.floor((resizedHeight - CROP_SIZE) / 2),
  };
}

function configureResizeContext(context: CanvasRenderingContext2D): void {
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
}

export async function prepareImage(image: InspectedImage): Promise<PreparedImage> {
  const bitmap = await createImageBitmap(image.file, { imageOrientation: "from-image" });
  try {
    const geometry = calculatePreprocessGeometry(bitmap.width, bitmap.height);
    const resizedCanvas = document.createElement("canvas");
    resizedCanvas.width = geometry.resizedWidth;
    resizedCanvas.height = geometry.resizedHeight;
    const resizeContext = resizedCanvas.getContext("2d", {
      alpha: false,
      colorSpace: "srgb",
    });
    if (!resizeContext) throw new Error("Canvas processing is unavailable in this browser.");
    configureResizeContext(resizeContext);
    resizeContext.drawImage(bitmap, 0, 0, geometry.resizedWidth, geometry.resizedHeight);

    const cropCanvas = document.createElement("canvas");
    cropCanvas.width = CROP_SIZE;
    cropCanvas.height = CROP_SIZE;
    const cropContext = cropCanvas.getContext("2d", {
      alpha: false,
      colorSpace: "srgb",
      willReadFrequently: true,
    });
    if (!cropContext) throw new Error("Canvas processing is unavailable in this browser.");
    cropContext.drawImage(
      resizedCanvas,
      geometry.cropLeft,
      geometry.cropTop,
      CROP_SIZE,
      CROP_SIZE,
      0,
      0,
      CROP_SIZE,
      CROP_SIZE,
    );

    // Geometry now mirrors Pillow. Canvas interpolation is implementation-defined, so exact
    // cross-runtime pixel parity still requires a Python↔browser golden-image test at release.
    const imageData = cropContext.getImageData(0, 0, CROP_SIZE, CROP_SIZE);
    const copy = new Uint8ClampedArray(imageData.data);
    resizedCanvas.width = 0;
    resizedCanvas.height = 0;
    cropCanvas.width = 0;
    cropCanvas.height = 0;
    return { width: 224, height: 224, rgba: copy.buffer };
  } finally {
    bitmap.close();
  }
}
