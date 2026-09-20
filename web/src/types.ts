export type PlateGaugeResult =
  | {
      status: "estimate";
      modelVersion: string;
      leftoverFraction: number;
      empiricalInterval90?: [number, number];
      remainingMassG?: number;
      remainingMassIntervalG?: [number, number];
      warnings: string[];
      processingMs: number;
    }
  | {
      status: "abstain";
      modelVersion: string;
      reasonCodes: string[];
      warnings: string[];
    }
  | {
      status: "invalid_input";
      errorCodes: string[];
    };

export type ModelState =
  | { status: "loading" }
  | { status: "ready"; modelVersion: string; isTestAdapter: boolean }
  | { status: "unavailable"; message: string };

export type ImageRole = "before" | "after";

export interface InspectedImage {
  file: File;
  width: number;
  height: number;
  aspectRatio: number;
  sha256: string;
  mediaType: "image/jpeg" | "image/png" | "image/webp";
}

export interface PreparedImage {
  width: 224;
  height: 224;
  rgba: ArrayBuffer;
}

export interface RawQuantiles {
  q05: number;
  q50: number;
  q95: number;
  modelVersion: string;
  intervalGatePassed: boolean;
  abstentionWidth: number;
  isTestAdapter: boolean;
  processingMs: number;
}

export type ModelErrorCode =
  | "MODEL_MANIFEST_MISSING"
  | "MODEL_MANIFEST_INVALID"
  | "MODEL_ARTIFACT_MISSING"
  | "MODEL_CHECKSUM_MISMATCH"
  | "MODEL_OUTPUT_INVALID"
  | "MODEL_RUNTIME_ERROR"
  | "MODEL_REQUEST_ABORTED"
  | "MODEL_REQUEST_TIMEOUT"
  | "MODEL_CLIENT_DISPOSED"
  | "WORKER_ERROR";

export class ModelError extends Error {
  readonly code: ModelErrorCode;

  constructor(code: ModelErrorCode, message: string) {
    super(message);
    this.name = "ModelError";
    this.code = code;
  }
}
