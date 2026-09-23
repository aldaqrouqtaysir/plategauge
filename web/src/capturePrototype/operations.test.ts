import { afterEach, describe, expect, it, vi } from "vitest";
import { boundedOperation, LOCAL_OPERATION_TIMEOUT_MS, LocalOperationError, wipeBuffer } from "./operations";

afterEach(() => vi.useRealTimers());

describe("bounded local operations", () => {
  it("returns a timely result and removes its deadline", async () => {
    vi.useFakeTimers();
    const dispose = vi.fn();
    await expect(boundedOperation(() => Promise.resolve(7), new AbortController().signal, dispose)).resolves.toBe(7);
    expect(vi.getTimerCount()).toBe(0);
    expect(dispose).not.toHaveBeenCalled();
  });
  it("does not start when already cancelled", async () => {
    const controller = new AbortController(); controller.abort();
    const operation = vi.fn();
    await expect(boundedOperation(operation, controller.signal, vi.fn())).rejects.toMatchObject({ code: "cancelled" });
    expect(operation).not.toHaveBeenCalled();
  });
  it("cancels immediately and disposes a late allocation exactly once", async () => {
    vi.useFakeTimers();
    const controller = new AbortController(); const dispose = vi.fn();
    let complete!: (value: number) => void;
    const pending = boundedOperation(() => new Promise<number>((resolve) => { complete = resolve; }), controller.signal, dispose);
    const failure = expect(pending).rejects.toBeInstanceOf(LocalOperationError);
    controller.abort(); await failure;
    complete(9); await Promise.resolve();
    expect(dispose).toHaveBeenCalledExactlyOnceWith(9);
    expect(vi.getTimerCount()).toBe(0);
  });
  it("times out a never-resolving decode and ignores late rejection", async () => {
    vi.useFakeTimers();
    let fail!: (reason: Error) => void;
    const pending = boundedOperation(() => new Promise((_resolve, reject) => { fail = reject; }), new AbortController().signal, vi.fn());
    const failure = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(LOCAL_OPERATION_TIMEOUT_MS); await failure;
    fail(new Error("late decode failure")); await Promise.resolve();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("disposes a successful result arriving after the timeout", async () => {
    vi.useFakeTimers(); const dispose = vi.fn(); let complete!: (value: number) => void;
    const pending = boundedOperation(() => new Promise<number>((resolve) => { complete = resolve; }), new AbortController().signal, dispose);
    const failure = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(LOCAL_OPERATION_TIMEOUT_MS); await failure;
    complete(3); await Promise.resolve(); expect(dispose).toHaveBeenCalledExactlyOnceWith(3);
  });
  it("propagates synchronous failure and clears its deadline", async () => {
    vi.useFakeTimers();
    await expect(boundedOperation(() => { throw new Error("failed"); }, new AbortController().signal, vi.fn())).rejects.toThrow("failed");
    expect(vi.getTimerCount()).toBe(0);
  });
  it.each([0, -1, NaN, Infinity, 15_001, 1.5])("rejects invalid timeout %s", async (timeout) => {
    await expect(boundedOperation(() => Promise.resolve(1), new AbortController().signal, vi.fn(), timeout)).rejects.toThrow("deadline");
  });
  it("wipes prepared pixels", () => {
    const data = new Uint8Array([1, 2, 3]); wipeBuffer(data.buffer); expect([...data]).toEqual([0, 0, 0]);
  });
});
