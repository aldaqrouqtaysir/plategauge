export interface ReleaseManifest {
  schemaVersion: 1;
  modelVersion: string;
  modelPath: string;
  modelSha256: string;
  beforeInputName: string;
  afterInputName: string;
  outputName: string;
  calibration: {
    lowerExpansion: number;
    upperExpansion: number;
    abstentionWidth: number;
    intervalGatePassed: boolean;
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSafeName(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9_.-]+$/.test(value);
}

function isUnitInterval(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

export function parseReleaseManifest(value: unknown): ReleaseManifest | null {
  if (!isRecord(value) || value.schemaVersion !== 1) return null;
  if (typeof value.modelVersion !== "string" || value.modelVersion.trim().length === 0) return null;
  if (
    typeof value.modelPath !== "string" ||
    !/^models\/[A-Za-z0-9_.-]+\.onnx$/.test(value.modelPath)
  ) {
    return null;
  }
  if (typeof value.modelSha256 !== "string" || !/^[a-f0-9]{64}$/.test(value.modelSha256)) {
    return null;
  }
  if (
    !isSafeName(value.beforeInputName) ||
    !isSafeName(value.afterInputName) ||
    !isSafeName(value.outputName)
  ) {
    return null;
  }
  if (!isRecord(value.calibration)) return null;
  const { calibration } = value;
  if (
    !isUnitInterval(calibration.lowerExpansion) ||
    !isUnitInterval(calibration.upperExpansion) ||
    !isUnitInterval(calibration.abstentionWidth) ||
    calibration.abstentionWidth === 0 ||
    typeof calibration.intervalGatePassed !== "boolean"
  ) {
    return null;
  }

  return {
    schemaVersion: 1,
    modelVersion: value.modelVersion,
    modelPath: value.modelPath,
    modelSha256: value.modelSha256,
    beforeInputName: value.beforeInputName,
    afterInputName: value.afterInputName,
    outputName: value.outputName,
    calibration: {
      lowerExpansion: calibration.lowerExpansion,
      upperExpansion: calibration.upperExpansion,
      abstentionWidth: calibration.abstentionWidth,
      intervalGatePassed: calibration.intervalGatePassed,
    },
  };
}
