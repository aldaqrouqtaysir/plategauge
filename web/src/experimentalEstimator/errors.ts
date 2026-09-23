const MESSAGES = {
  unavailable_context: "Estimation is available only in the approved secure candidate or local preview.",
  cancelled: "Estimate cancelled. No result was kept.",
  mismatched_shape: "Retake the pair with the same camera orientation and framing.",
  invalid_input: "The captured model input is invalid. Retake the photos.",
  identical_pair: "These model views are identical. Capture distinct before and after photos.",
  timeout: "Estimation took too long. Your photos remain available. Retry, or try a supported browser on a more capable device.",
  invalid_result: "The local model could not produce a valid estimate. Your photos remain available. Try again; no result was kept.",
  worker_failed: "The browser model stopped unexpectedly. Your photos remain available. Try again.",
  unreadable_result: "The browser could not read the model result. Your photos remain available. Try again.",
  transfer_failed: "The browser could not prepare the model request. Your photos remain available. Try again.",
  unknown: "The local model could not produce an estimate. Your photos remain available. Retry, or retake the pair if the problem continues.",
} as const;

export type EstimateErrorCode = keyof typeof MESSAGES;

export class EstimateError extends Error {
  constructor(readonly code: EstimateErrorCode) {
    super(MESSAGES[code]);
    this.name = "EstimateError";
  }
}

/** Only application-owned codes reach the UI, never exception strings or image data. */
export function estimateErrorMessage(error: unknown): string {
  return error instanceof EstimateError && Object.hasOwn(MESSAGES, error.code)
    ? MESSAGES[error.code]
    : MESSAGES.unknown;
}
