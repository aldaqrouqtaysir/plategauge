import { pillowCropGeometry } from "../libv2/pillowResize";

/** Percentages in an unmirrored, full-frame preview; uses the inference geometry. */
export function getModelCropFrame(width: number, height: number): { left: number; top: number; width: number; height: number } {
  const geometry = pillowCropGeometry(width, height);
  return {
    left: geometry.cropLeft / geometry.resizedWidth * 100,
    top: geometry.cropTop / geometry.resizedHeight * 100,
    width: 224 / geometry.resizedWidth * 100,
    height: 224 / geometry.resizedHeight * 100,
  };
}
