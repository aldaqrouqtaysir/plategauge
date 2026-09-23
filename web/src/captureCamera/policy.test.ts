import { describe, expect, it } from "vitest";
import { localCaptureMode, localPreviewView } from "./policy";

describe("local camera and separate fixture routes", () => {
  it.each(["localhost", "127.0.0.1", "[::1]", "::1"])("allows explicit camera preview only on loopback %s", (host) => {
    expect(localCaptureMode(true, host, "?capture=1")).toBe("camera");
    expect(localCaptureMode(true, host, "?capturePrototype=1")).toBe("camera");
    expect(localCaptureMode(true, host, "?captureFixtures=1")).toBe("fixtures");
  });
  it.each(["", "?capture=0", "?capture=1&capture=0", "?captureFixtures=1&capturePrototype=1", "?captureFixtures=1&captureFixtures=1"])("rejects missing/ambiguous mode %s", (query) => expect(localCaptureMode(true, "localhost", query)).toBeNull());
  it.each(["example.com", "127.0.0.1.example.com", "192.168.1.2"])("does not expose camera over other origins %s", (host) => expect(localCaptureMode(true, host, "?capture=1")).toBeNull());
  it.each(["?capture=1", "?capturePrototype=1", "?captureFixtures=1"])("never enables production %s", (query) => expect(localCaptureMode(false, "localhost", query)).toBeNull());
});

describe("capture-first local view selection", () => {
  it.each(["localhost", "127.0.0.1", "[::1]", "::1"])("opens local home and explicit views on %s", (host) => {
    expect(localPreviewView(true, host, "")).toBe("home");
    expect(localPreviewView(true, host, "?view=evidence")).toBe("evidence");
    expect(localPreviewView(true, host, "?benchmark=1")).toBe("evidence");
    expect(localPreviewView(true, host, "?capture=1")).toBe("camera");
    expect(localPreviewView(true, host, "?capturePrototype=1")).toBe("camera");
    expect(localPreviewView(true, host, "?captureFixtures=1")).toBe("fixtures");
  });
  it.each([
    "?view=unknown", "?capture=0", "?benchmark=0", "?unknown=1",
    "?view=evidence&view=evidence", "?benchmark=1&benchmark=1",
    "?view=evidence&capture=1", "?benchmark=1&capture=1",
    "?capture=1&captureFixtures=1", "?capture=1&capturePrototype=1",
    "?capture=1&unknown=1", "?view=evidence&benchmark=1",
  ])("falls back to the benchmark for unsupported/ambiguous query %s", (query) => {
    expect(localPreviewView(true, "localhost", query)).toBeNull();
  });
  it.each(["", "?view=evidence", "?capture=1", "?benchmark=1", "?captureFixtures=1"])("keeps production isolated for %s", (query) => {
    expect(localPreviewView(false, "localhost", query)).toBeNull();
  });
  it.each(["example.com", "localhost.example.com", "127.0.0.1.example.com", "192.168.1.2"])("keeps non-loopback development isolated on %s", (host) => {
    expect(localPreviewView(true, host, "")).toBeNull();
    expect(localPreviewView(true, host, "?capture=1")).toBeNull();
    expect(localPreviewView(true, host, "?view=evidence")).toBeNull();
  });
});
