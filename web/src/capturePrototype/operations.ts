/** Bounded local work; cancellation never accepts a stale result. */
export const LOCAL_OPERATION_TIMEOUT_MS = 15_000;

export class LocalOperationError extends Error {
  constructor(readonly code: "cancelled" | "timeout") {
    super(code === "timeout"
      ? "The local image check took too long. Try again or reset the session."
      : "Local preparation was cancelled.");
    this.name = "LocalOperationError";
  }
}

export function boundedOperation<T>(
  operation: () => Promise<T>,
  signal: AbortSignal,
  disposeLate: (value: T) => void,
  timeoutMs = LOCAL_OPERATION_TIMEOUT_MS,
): Promise<T> {
  if (signal.aborted) return Promise.reject(new LocalOperationError("cancelled"));
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > LOCAL_OPERATION_TIMEOUT_MS) {
    return Promise.reject(new Error("Invalid local-operation deadline."));
  }
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const release = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
    };
    const fail = (reason: unknown) => {
      if (settled) return;
      settled = true;
      release();
      reject(reason instanceof Error ? reason : new Error("The local image operation failed."));
    };
    const onAbort = () => fail(new LocalOperationError("cancelled"));
    const timer = setTimeout(() => fail(new LocalOperationError("timeout")), timeoutMs);
    signal.addEventListener("abort", onAbort, { once: true });
    try {
      operation().then((value) => {
        if (settled) {
          // Disposal functions must not retain or log image content.
          disposeLate(value);
          return;
        }
        settled = true;
        release();
        resolve(value);
      }, fail).catch(fail);
    } catch (cause) {
      fail(cause);
    }
  });
}

export function wipeBuffer(buffer: ArrayBuffer): void {
  if (buffer.byteLength > 0) new Uint8Array(buffer).fill(0);
}
