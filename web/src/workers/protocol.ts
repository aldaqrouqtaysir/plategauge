import type { ModelErrorCode, PreparedImage, RawQuantiles } from "../types";

export type ModelWorkerRequest =
  | { type: "init"; requestId: number }
  | {
      type: "infer";
      requestId: number;
      before: PreparedImage;
      after: PreparedImage;
    }
  | { type: "dispose"; requestId: number };

export type ModelWorkerResponse =
  | {
      type: "ready";
      requestId: number;
      modelVersion: string;
      isTestAdapter: boolean;
    }
  | { type: "result"; requestId: number; result: RawQuantiles }
  | { type: "disposed"; requestId: number }
  | {
      type: "error";
      requestId: number;
      code: ModelErrorCode;
      message: string;
    };
