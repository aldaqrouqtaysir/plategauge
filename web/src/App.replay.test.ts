import { createElement } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { ModelError, type RawQuantiles } from "./types";

const modelMocks = vi.hoisted(() => ({
  initialize: vi.fn(),
  predictBound: vi.fn(),
  dispose: vi.fn(),
}));

vi.mock("./lib/modelClient", () => ({
  ModelClient: class {
    initialize = modelMocks.initialize;
    predictBound = modelMocks.predictBound;
    dispose = modelMocks.dispose;
  },
}));

vi.mock("./lib/imageValidation", () => ({
  inspectImage: vi.fn((file: File) =>
    Promise.resolve({
      file,
      width: 640,
      height: 480,
      aspectRatio: 4 / 3,
      sha256: `sha256-${file.name}`,
      mediaType: "image/jpeg",
    }),
  ),
  validatePair: vi.fn(),
}));

vi.mock("./lib/preprocess", () => ({
  prepareImage: vi.fn(() =>
    Promise.resolve({
      width: 224,
      height: 224,
      rgba: new ArrayBuffer(224 * 224 * 4),
    }),
  ),
}));

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}

interface ReplayBinding {
  sampleId: string;
  replayId: number;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function rawResult(overrides: Partial<RawQuantiles> = {}): RawQuantiles {
  return {
    q05: 0.12,
    q50: 0.31,
    q95: 0.58,
    modelVersion: "benchmark-v1",
    intervalGatePassed: false,
    abstentionWidth: 0.3,
    isTestAdapter: false,
    processingMs: 21,
    ...overrides,
  };
}

beforeEach(() => {
  window.history.replaceState({}, "", "/?benchmark=1");
  modelMocks.initialize.mockReset();
  modelMocks.predictBound.mockReset();
  modelMocks.dispose.mockReset();
  modelMocks.initialize.mockResolvedValue({
    status: "ready",
    modelVersion: "benchmark-v1",
    isTestAdapter: false,
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(new Blob(["fixed-example"], { type: "image/jpeg" }), { status: 200 }),
      ),
    ),
  );
});

describe("fixed replay reliability", () => {
  it("aborts a prior sample replay and ignores its stale completion", async () => {
    const first = deferred<{ binding: ReplayBinding; result: RawQuantiles }>();
    const second = deferred<{ binding: ReplayBinding; result: RawQuantiles }>();
    modelMocks.predictBound
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    render(createElement(App));

    await screen.findByText("Bundled pair lefood-0192 ready.");
    fireEvent.click(screen.getByTestId("run-fixed-example"));
    await waitFor(() => expect(modelMocks.predictBound).toHaveBeenCalledTimes(1));
    const firstBinding = modelMocks.predictBound.mock.calls[0]![0] as ReplayBinding;
    const firstSignal = (modelMocks.predictBound.mock.calls[0]![3] as { signal: AbortSignal })
      .signal;
    expect(modelMocks.predictBound.mock.calls[0]![3]).toMatchObject({ timeoutMs: 15_000 });

    fireEvent.click(screen.getByTestId("example-lefood-0461"));
    expect(firstSignal.aborted).toBe(true);
    await act(async () => {
      first.resolve({ binding: firstBinding, result: rawResult({ processingMs: 999 }) });
      await first.promise;
    });
    expect(screen.queryByTestId("runtime-output")).not.toBeInTheDocument();

    await screen.findByText("Bundled pair lefood-0461 ready.");
    fireEvent.click(screen.getByTestId("run-fixed-example"));
    await waitFor(() => expect(modelMocks.predictBound).toHaveBeenCalledTimes(2));
    const secondBinding = modelMocks.predictBound.mock.calls[1]![0] as ReplayBinding;
    expect(secondBinding.sampleId).toBe("lefood-0461");
    expect(secondBinding.replayId).toBeGreaterThan(firstBinding.replayId);

    await act(async () => {
      second.resolve({ binding: secondBinding, result: rawResult() });
      await second.promise;
    });
    const output = await screen.findByTestId("runtime-output");
    expect(output).toHaveAttribute("data-sample-id", "lefood-0461");
    expect(output).toHaveAttribute("data-replay-id", String(secondBinding.replayId));
    expect(output).not.toHaveTextContent("31%");
  });

  it.each([
    ["MODEL_REQUEST_TIMEOUT", "The browser model did not respond within 15000 milliseconds."],
    ["WORKER_ERROR", "The browser model worker stopped unexpectedly."],
  ] as const)("surfaces terminal %s failures and disables further replay", async (code, message) => {
    modelMocks.predictBound.mockRejectedValueOnce(new ModelError(code, message));
    render(createElement(App));

    await screen.findByText("Bundled pair lefood-0192 ready.");
    fireEvent.click(screen.getByTestId("run-fixed-example"));

    await waitFor(() => {
      expect(screen.getByTestId("run-fixed-example")).toBeDisabled();
      expect(screen.getAllByRole("alert").some((alert) => alert.textContent?.includes(message))).toBe(
        true,
      );
    });
    expect(screen.queryByTestId("runtime-output")).not.toBeInTheDocument();
  });

  it("announces a bundled-asset failure as an alert", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(null, { status: 404 }))),
    );
    render(createElement(App));

    const failure = await screen.findByText(/Bundled pair unavailable:/);
    expect(failure).toHaveAttribute("role", "alert");
    expect(screen.getByTestId("run-fixed-example")).toBeDisabled();
  });

  it("shows a non-substituting visible error when a displayed example image fails", () => {
    window.history.replaceState({}, "", "/");
    render(createElement(App));

    fireEvent.error(
      screen.getByAltText("Before photograph for LeFood sample lefood-0192"),
    );

    expect(screen.getByTestId("fixed-image-error")).toHaveTextContent(
      "No substitute image was used",
    );
    expect(screen.getByText("Before image unavailable")).toBeInTheDocument();
  });

  it("aborts an active replay and disposes the worker on unmount", async () => {
    const pending = deferred<{ binding: ReplayBinding; result: RawQuantiles }>();
    modelMocks.predictBound.mockImplementationOnce(() => pending.promise);
    const view = render(createElement(App));

    await screen.findByText("Bundled pair lefood-0192 ready.");
    fireEvent.click(screen.getByTestId("run-fixed-example"));
    await waitFor(() => expect(modelMocks.predictBound).toHaveBeenCalledTimes(1));
    const signal = (modelMocks.predictBound.mock.calls[0]![3] as { signal: AbortSignal }).signal;

    view.unmount();

    expect(signal.aborted).toBe(true);
    expect(modelMocks.dispose).toHaveBeenCalledTimes(1);
  });
});
