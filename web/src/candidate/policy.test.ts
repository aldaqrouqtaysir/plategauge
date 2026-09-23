import { describe, expect, it } from "vitest";
import { candidateContextAllowed, candidateView } from "./policy";

describe("camera candidate boundary", () => {
  it.each(["localhost", "127.0.0.1", "[::1]", "::1"])("allows secure loopback preview on %s", (host) => {
    expect(candidateContextAllowed(true, host, "http:", true, true)).toBe(true);
    expect(candidateContextAllowed(true, host, "https:", true, true)).toBe(true);
  });
  it("permits only the specified HTTPS deployment host outside loopback", () => {
    expect(candidateContextAllowed(true, "aldaqrouqtaysir.github.io", "https:", true, true)).toBe(true);
    expect(candidateContextAllowed(true, "aldaqrouqtaysir.github.io", "http:", true, true)).toBe(false);
  });
  it.each(["example.com", "localhost.example.com", "127.0.0.1.example.com", "192.168.1.2", "aldaqrouqtaysir.github.io.example.com"])("rejects unrelated host %s", (host) => {
    expect(candidateContextAllowed(true, host, "https:", true, true)).toBe(false);
  });
  it("rejects disabled builds, insecure contexts, frames and unsupported protocols", () => {
    expect(candidateContextAllowed(false, "localhost", "http:", true, true)).toBe(false);
    expect(candidateContextAllowed(true, "localhost", "http:", false, true)).toBe(false);
    expect(candidateContextAllowed(true, "localhost", "http:", true, false)).toBe(false);
    for (const protocol of ["file:", "data:", "blob:", "javascript:"]) {
      expect(candidateContextAllowed(true, "localhost", protocol, true, true)).toBe(false);
    }
  });
  it("routes only explicit supported selectors", () => {
    expect(candidateView("")).toBe("home");
    expect(candidateView("?capture=1")).toBe("camera");
    expect(candidateView("?view=evidence")).toBe("evidence");
  });
  it.each(["?capture=0", "?capture=1&capture=1", "?view=evidence&capture=1", "?captureFixtures=1", "?capturePrototype=1", "?benchmark=1", "?unknown=1", "?capture=1&x=1"])("falls back safely for %s", (query) => {
    expect(candidateView(query)).toBe("home");
  });
});
