import { useEffect, useRef } from "react";
import type { CameraPhoto } from "./camera";

/** Displays the retained model pixels, never a recrop of the lossy review JPEG. */
export default function ModelCropPreview({ photo, label }: { photo: CameraPhoto; label: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fallbackRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const fallback = fallbackRef.current;
    if (!canvas || !fallback) return;
    let pixels: ReturnType<CameraPhoto["copyPixels"]> | undefined;
    let imageData: ImageData | undefined;
    let context: CanvasRenderingContext2D | null = null;
    canvas.hidden = false;
    fallback.hidden = true;
    try {
      context = canvas.getContext("2d");
      if (!context) throw new Error("Preview canvas is unavailable");
      pixels = photo.copyPixels();
      if (pixels.width !== 224 || pixels.height !== 224 || pixels.data.length !== 224 * 224 * 4) {
        throw new Error("Unexpected model crop dimensions");
      }
      imageData = context.createImageData(224, 224);
      imageData.data.set(pixels.data);
      context.putImageData(imageData, 0, 0);
    } catch {
      context?.clearRect(0, 0, 224, 224);
      canvas.hidden = true;
      fallback.hidden = false;
    } finally {
      pixels?.data.fill(0);
      imageData?.data.fill(0);
    }
    return () => { context?.clearRect(0, 0, 224, 224); };
  }, [photo]);
  return <div className="rc-model-crop-preview">
    <canvas ref={canvasRef} width={224} height={224} role="img" aria-label={label} data-testid="model-crop-preview" />
    <p ref={fallbackRef} hidden>Model view unavailable. Switch to Full photos to review or retake the pair.</p>
  </div>;
}
