import { afterEach, describe, expect, it, vi } from "vitest";

import type { PreparedImage, RawQuantiles } from "../types";
import type { ModelWorkerRequest } from "../workers/protocol";
import { ModelClient } from "./modelClient";

type WorkerListener = (event: Event) => void;

class FakeWorker {
  readonly posted: ModelWorkerRequest[] = [];
  terminated = false;
  throwOnPost = false;
  private readonly listeners = new Map<string, Set<WorkerListener>>();

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    const listeners = this.listeners.get(type) ?? new Set<WorkerListener>();
    listeners.add(this.asListener(listener));
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.get(type)?.delete(this.asListener(listener));
  }

  postMessage(message: ModelWorkerRequest): void {
    if (this.throwOnPost) throw new DOMException("worker is unavailable", "InvalidStateError");
    this.posted.push(message);
  }

  terminate(): void {
    this.terminated = true;
  }

  respond(response: unknown): void {
    this.dispatch("message", new MessageEvent("message", { data: response }));
  }

  fail(type: "error" | "messageerror"): void {
    this.dispatch(type, new Event(type));
  }

  private dispatch(type: string, event: Event): void {
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }

  private asListener(listener: EventListenerOrEventListenerObject): WorkerListener {
    if (typeof listener === "function") return listener;
    return (event) => listener.handleEvent(event);
  }
}

function createClient(worker: FakeWorker, requestTimeoutMs = 1_000): ModelClient {
  return new ModelClient({
    requestTimeoutMs,
    workerFactory: () => worker as unknown as Worker,
  });
}

function preparedImage(): PreparedImage {
  return {
    width: 224,
    height: 224,
    rgba: new ArrayBuffer(224 * 224 * 4),
  };
}

const rawResult: RawQuantiles = {
  q05: 0.12,
  q50: 0.31,
  q95: 0.58,
  modelVersion: "benchmark-v1",
  intervalGatePassed: false,
  abstentionWidth: 0.3,
  isTestAdapter: false,
  processingMs: 18,
};

afterEach(() => {
  vi.useRealTimers();
});

describe("ModelClient", () => {
  it("preserves a replay binding so callers can reject stale completions", async () => {
    const worker = new FakeWorker();
    const client = createClient(worker);

    const initializing = client.initialize();
    expect(worker.posted[0]).toMatchObject({ type: "init", requestId: 1 });
    worker.respond({
      type: "ready",
      requestId: 1,
      modelVersion: "benchmark-v1",
      isTestAdapter: false,
    });
    await expect(initializing).resolves.toEqual({
      status: "ready",
      modelVersion: "benchmark-v1",
      isTestAdapter: false,
    });

    const binding = { sampleId: "sample-019", replayId: 7 };
    const prediction = client.predictBound(binding, preparedImage(), preparedImage());
    expect(worker.posted[1]).toMatchObject({ type: "infer", requestId: 2 });
    worker.respond({ type: "result", requestId: 2, result: rawResult });

    await expect(prediction).resolves.toEqual({ binding, result: rawResult });
    expect(client.status).toBe("active");
    client.dispose();
  });

  it("cancels one request without disabling the worker and ignores its late response", async () => {
    const worker = new FakeWorker();
    const client = createClient(worker);
    const controller = new AbortController();

    const cancelled = client.initialize({ signal: controller.signal });
    const cancellation = expect(cancelled).rejects.toMatchObject({
      code: "MODEL_REQUEST_ABORTED",
    });
    controller.abort();
    await cancellation;

    worker.respond({
      type: "ready",
      requestId: 1,
      modelVersion: "late-response",
      isTestAdapter: false,
    });
    expect(client.status).toBe("active");

    const retry = client.initialize();
    worker.respond({
      type: "ready",
      requestId: 2,
      modelVersion: "retry-v1",
      isTestAdapter: false,
    });
    await expect(retry).resolves.toMatchObject({ modelVersion: "retry-v1" });
    client.dispose();
  });

  it("does not post a request whose signal is already aborted", async () => {
    const worker = new FakeWorker();
    const client = createClient(worker);
    const controller = new AbortController();
    controller.abort();

    await expect(client.initialize({ signal: controller.signal })).rejects.toMatchObject({
      code: "MODEL_REQUEST_ABORTED",
    });
    expect(worker.posted).toHaveLength(0);
    expect(client.status).toBe("active");
    client.dispose();
  });

  it("can cancel all pending work without disabling later requests", async () => {
    const worker = new FakeWorker();
    const client = createClient(worker);
    const first = client.initialize();
    const second = client.initialize();
    const firstCancellation = expect(first).rejects.toMatchObject({
      code: "MODEL_REQUEST_ABORTED",
      message: "The selected sample changed.",
    });
    const secondCancellation = expect(second).rejects.toMatchObject({
      code: "MODEL_REQUEST_ABORTED",
      message: "The selected sample changed.",
    });

    client.cancelPending("The selected sample changed.");
    await Promise.all([firstCancellation, secondCancellation]);
    expect(client.status).toBe("active");

    const retry = client.initialize();
    worker.respond({
      type: "ready",
      requestId: 3,
      modelVersion: "retry-v1",
      isTestAdapter: false,
    });
    await expect(retry).resolves.toMatchObject({ modelVersion: "retry-v1" });
    client.dispose();
  });

  it("fails closed after a bounded request timeout", async () => {
    vi.useFakeTimers();
    const worker = new FakeWorker();
    const client = createClient(worker, 25);

    const initializing = client.initialize();
    const timedOut = expect(initializing).rejects.toMatchObject({
      code: "MODEL_REQUEST_TIMEOUT",
    });
    await vi.advanceTimersByTimeAsync(25);
    await timedOut;

    expect(client.status).toBe("failed");
    expect(worker.terminated).toBe(true);
    await expect(client.initialize()).rejects.toMatchObject({
      code: "MODEL_REQUEST_TIMEOUT",
    });
    client.dispose();
  });

  it.each(["error", "messageerror"] as const)(
    "rejects every pending request and disables the client after worker %s",
    async (eventType) => {
      const worker = new FakeWorker();
      const client = createClient(worker);
      const first = client.initialize();
      const second = client.initialize();
      const firstFailure = expect(first).rejects.toMatchObject({ code: "WORKER_ERROR" });
      const secondFailure = expect(second).rejects.toMatchObject({ code: "WORKER_ERROR" });

      worker.fail(eventType);

      await Promise.all([firstFailure, secondFailure]);
      expect(client.status).toBe("failed");
      expect(worker.terminated).toBe(true);
      await expect(client.initialize()).rejects.toMatchObject({ code: "WORKER_ERROR" });
      client.dispose();
    },
  );

  it("rejects pending and future work when disposed and remains idempotent", async () => {
    const worker = new FakeWorker();
    const client = createClient(worker);
    const initializing = client.initialize();
    const disposed = expect(initializing).rejects.toMatchObject({
      code: "MODEL_CLIENT_DISPOSED",
    });

    client.dispose();
    await disposed;

    expect(client.status).toBe("disposed");
    expect(worker.terminated).toBe(true);
    expect(worker.posted.at(-1)).toMatchObject({ type: "dispose" });
    const postCount = worker.posted.length;
    client.dispose();
    expect(worker.posted).toHaveLength(postCount);
    await expect(client.initialize()).rejects.toMatchObject({
      code: "MODEL_CLIENT_DISPOSED",
    });
  });

  it("fails closed if postMessage throws", async () => {
    const worker = new FakeWorker();
    worker.throwOnPost = true;
    const client = createClient(worker);

    await expect(client.initialize()).rejects.toMatchObject({ code: "WORKER_ERROR" });
    expect(client.status).toBe("failed");
    expect(worker.terminated).toBe(true);
    client.dispose();
  });

  it("fails closed on a mismatched worker response", async () => {
    const worker = new FakeWorker();
    const client = createClient(worker);
    const initializing = client.initialize();
    const failed = expect(initializing).rejects.toMatchObject({ code: "WORKER_ERROR" });

    worker.respond({ type: "result", requestId: 1, result: rawResult });

    await failed;
    expect(client.status).toBe("failed");
    expect(worker.terminated).toBe(true);
    client.dispose();
  });

  it("rejects invalid timeout configuration", () => {
    const worker = new FakeWorker();
    expect(
      () => new ModelClient({ requestTimeoutMs: 0, workerFactory: () => worker as unknown as Worker }),
    ).toThrow("finite positive");
  });
});
