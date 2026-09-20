import type { ModelState, PreparedImage, RawQuantiles } from "../types";
import { ModelError } from "../types";
import type { ModelWorkerRequest, ModelWorkerResponse } from "../workers/protocol";

type ModelClientStatus = "active" | "failed" | "disposed";
type SuccessfulResponse = Exclude<ModelWorkerResponse, { type: "error" }>;
type SuccessfulResponseType = SuccessfulResponse["type"];

interface PendingRequest {
  expectedType: SuccessfulResponseType;
  resolve: (value: SuccessfulResponse) => void;
  reject: (reason: unknown) => void;
  timeoutId: ReturnType<typeof setTimeout>;
  removeAbortListener?: () => void;
}

export interface ModelRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface ModelClientOptions {
  requestTimeoutMs?: number;
  workerFactory?: () => Worker;
}

export interface BoundPrediction<TBinding> {
  binding: TBinding;
  result: RawQuantiles;
}

export const DEFAULT_MODEL_REQUEST_TIMEOUT_MS = 60_000;

export class ModelClient {
  private worker: Worker | null = null;
  private readonly pending = new Map<number, PendingRequest>();
  private readonly requestTimeoutMs: number;
  private nextRequestId = 1;
  private clientStatus: ModelClientStatus = "active";
  private terminalError: ModelError | null = null;

  private readonly handleMessage = (event: MessageEvent<ModelWorkerResponse>): void => {
    const response = event.data;
    if (!this.isResponseEnvelope(response)) {
      this.failTerminal(
        new ModelError("WORKER_ERROR", "The browser model worker returned an invalid response."),
      );
      return;
    }

    const request = this.pending.get(response.requestId);
    // A cancelled request can still finish in the worker. Its late response is intentionally ignored.
    if (!request) return;

    if (response.type === "error") {
      this.rejectRequest(
        response.requestId,
        new ModelError(response.code, response.message),
      );
      return;
    }

    if (response.type !== request.expectedType) {
      this.failTerminal(
        new ModelError(
          "WORKER_ERROR",
          `The browser model worker returned ${response.type} for a ${request.expectedType} request.`,
        ),
      );
      return;
    }

    this.resolveRequest(response.requestId, response);
  };

  private readonly handleWorkerFailure = (): void => {
    this.failTerminal(
      new ModelError("WORKER_ERROR", "The browser model worker stopped unexpectedly."),
    );
  };

  constructor(options: ModelClientOptions = {}) {
    this.requestTimeoutMs = this.validateTimeout(
      options.requestTimeoutMs ?? DEFAULT_MODEL_REQUEST_TIMEOUT_MS,
    );

    try {
      this.worker =
        options.workerFactory?.() ??
        new Worker(new URL("../workers/model.worker.ts", import.meta.url), {
          type: "module",
          name: "plategauge-model",
        });
      this.worker.addEventListener("message", this.handleMessage);
      this.worker.addEventListener("error", this.handleWorkerFailure);
      this.worker.addEventListener("messageerror", this.handleWorkerFailure);
    } catch {
      this.clientStatus = "failed";
      this.terminalError = new ModelError(
        "WORKER_ERROR",
        "The browser model worker could not be started.",
      );
      this.worker = null;
    }
  }

  get status(): ModelClientStatus {
    return this.clientStatus;
  }

  async initialize(
    options: ModelRequestOptions = {},
  ): Promise<Extract<ModelState, { status: "ready" }>> {
    const requestId = this.allocateRequestId();
    const response = await this.send<Extract<ModelWorkerResponse, { type: "ready" }>>({
      type: "init",
      requestId,
    }, "ready", [], options);
    return {
      status: "ready",
      modelVersion: response.modelVersion,
      isTestAdapter: response.isTestAdapter,
    };
  }

  async predict(
    before: PreparedImage,
    after: PreparedImage,
    options: ModelRequestOptions = {},
  ): Promise<RawQuantiles> {
    const requestId = this.allocateRequestId();
    const response = await this.send<Extract<ModelWorkerResponse, { type: "result" }>>(
      {
        type: "infer",
        requestId,
        before,
        after,
      },
      "result",
      [before.rgba, after.rgba],
      options,
    );
    return response.result;
  }

  async predictBound<TBinding>(
    binding: TBinding,
    before: PreparedImage,
    after: PreparedImage,
    options: ModelRequestOptions = {},
  ): Promise<BoundPrediction<TBinding>> {
    const result = await this.predict(before, after, options);
    return { binding, result };
  }

  cancelPending(message = "The browser model request was cancelled."): void {
    const error = new ModelError("MODEL_REQUEST_ABORTED", message);
    for (const requestId of [...this.pending.keys()]) {
      this.rejectRequest(requestId, error);
    }
  }

  dispose(): void {
    if (this.clientStatus === "disposed") return;

    const worker = this.worker;
    this.worker = null;
    this.clientStatus = "disposed";
    this.terminalError = new ModelError(
      "MODEL_CLIENT_DISPOSED",
      "The browser model client has been disposed.",
    );

    this.detachWorker(worker);
    if (worker) {
      try {
        worker.postMessage({
          type: "dispose",
          requestId: this.allocateRequestId(),
        } satisfies ModelWorkerRequest);
      } catch {
        // The client is already terminal; disposal remains complete even if notification fails.
      }
      try {
        worker.terminate();
      } catch {
        // Pending promises are still rejected below even if a nonstandard worker wrapper throws.
      }
    }
    this.rejectAll(this.terminalError);
  }

  private send<T extends ModelWorkerResponse>(
    request: ModelWorkerRequest,
    expectedType: SuccessfulResponseType,
    transfer: Transferable[] = [],
    options: ModelRequestOptions = {},
  ): Promise<T> {
    if (this.clientStatus !== "active" || !this.worker) {
      return Promise.reject(
        this.terminalError ??
          new ModelError("WORKER_ERROR", "The browser model client is unavailable."),
      );
    }

    const timeoutMs = this.validateTimeout(options.timeoutMs ?? this.requestTimeoutMs);
    if (options.signal?.aborted) {
      return Promise.reject(
        new ModelError("MODEL_REQUEST_ABORTED", "The browser model request was cancelled."),
      );
    }

    const worker = this.worker;
    const requestId = request.requestId;
    return new Promise<T>((resolve, reject) => {
      const abort = (): void => {
        this.rejectRequest(
          requestId,
          new ModelError("MODEL_REQUEST_ABORTED", "The browser model request was cancelled."),
        );
      };
      const timeoutId = setTimeout(() => {
        this.failTerminal(
          new ModelError(
            "MODEL_REQUEST_TIMEOUT",
            `The browser model did not respond within ${timeoutMs} milliseconds.`,
          ),
        );
      }, timeoutMs);

      this.pending.set(requestId, {
        expectedType,
        resolve: (value) => resolve(value as T),
        reject,
        timeoutId,
        removeAbortListener: options.signal
          ? () => options.signal?.removeEventListener("abort", abort)
          : undefined,
      });
      options.signal?.addEventListener("abort", abort, { once: true });

      try {
        worker.postMessage(request, transfer);
      } catch {
        this.failTerminal(
          new ModelError("WORKER_ERROR", "The browser model worker could not accept a request."),
        );
      }
    });
  }

  private allocateRequestId(): number {
    const requestId = this.nextRequestId;
    this.nextRequestId += 1;
    return requestId;
  }

  private validateTimeout(timeoutMs: number): number {
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
      throw new RangeError("Model request timeout must be a finite positive number.");
    }
    return timeoutMs;
  }

  private isResponseEnvelope(value: unknown): value is ModelWorkerResponse {
    if (!value || typeof value !== "object") return false;
    const candidate = value as { requestId?: unknown; type?: unknown };
    return Number.isSafeInteger(candidate.requestId) && typeof candidate.type === "string";
  }

  private resolveRequest(requestId: number, response: SuccessfulResponse): void {
    const request = this.takeRequest(requestId);
    request?.resolve(response);
  }

  private rejectRequest(requestId: number, error: ModelError): void {
    const request = this.takeRequest(requestId);
    request?.reject(error);
  }

  private takeRequest(requestId: number): PendingRequest | undefined {
    const request = this.pending.get(requestId);
    if (!request) return undefined;
    this.pending.delete(requestId);
    clearTimeout(request.timeoutId);
    request.removeAbortListener?.();
    return request;
  }

  private rejectAll(error: ModelError): void {
    for (const requestId of [...this.pending.keys()]) {
      this.rejectRequest(requestId, error);
    }
  }

  private failTerminal(error: ModelError): void {
    if (this.clientStatus !== "active") return;
    this.clientStatus = "failed";
    this.terminalError = error;

    const worker = this.worker;
    this.worker = null;
    this.detachWorker(worker);
    try {
      worker?.terminate();
    } catch {
      // Terminal state and pending-request rejection do not depend on termination succeeding.
    }
    this.rejectAll(error);
  }

  private detachWorker(worker: Worker | null): void {
    if (!worker) return;
    worker.removeEventListener("message", this.handleMessage);
    worker.removeEventListener("error", this.handleWorkerFailure);
    worker.removeEventListener("messageerror", this.handleWorkerFailure);
  }
}
