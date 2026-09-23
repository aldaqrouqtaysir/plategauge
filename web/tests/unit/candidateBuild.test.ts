// @vitest-environment node
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadEnv } from "vite";
import type * as ViteModule from "vite";
import config from "../../vite.config";

vi.mock("vite", async (original) => {
  const actual = await original<typeof ViteModule>();
  return { ...actual, loadEnv: vi.fn(actual.loadEnv) };
});

const createConfig = config;
const source = "https://github.com/aldaqrouqtaysir/plategauge/tree/a8c95adaa3a8f803d4e375330dde42e4706c6dee";
beforeEach(() => {
  // Vitest exports compiled VITE definitions to its workers; each config case
  // needs a clean input environment, not the already-compiled test flags.
  vi.stubEnv("VITE_PLATEGAUGE_CAMERA_CANDIDATE", undefined);
  vi.stubEnv("VITE_PLATEGAUGE_TEST_MODEL", undefined);
  vi.stubEnv("VITE_SOURCE_URL", undefined);
});
afterEach(() => { vi.unstubAllEnvs(); vi.mocked(loadEnv).mockRestore(); });

describe("explicit camera build contract", () => {
  it("keeps the ordinary production build camera-disabled", () => {
    vi.stubEnv("VITE_SOURCE_URL", source);
    const result = createConfig({ command: "build", mode: "production" });
    expect(result.build?.outDir).toBe("dist");
    expect(result.define?.["import.meta.env.VITE_PLATEGAUGE_CAMERA_CANDIDATE"]).toBe('"0"');
    expect(result.define?.["import.meta.env.VITE_PLATEGAUGE_TEST_MODEL"]).toBe('""');
  });
  it("creates a separate static candidate with no source maps", () => {
    vi.stubEnv("VITE_SOURCE_URL", source);
    const result = createConfig({ command: "build", mode: "camera-candidate" });
    expect(result.build?.outDir).toBe("dist-camera");
    expect(result.build?.sourcemap).toBe(false);
    expect(result.define?.["import.meta.env.VITE_PLATEGAUGE_CAMERA_CANDIDATE"]).toBe('"1"');
    expect(result.define?.["import.meta.env.VITE_PLATEGAUGE_TEST_MODEL"]).toBe('""');
  });
  it("cannot enable camera capability by injecting an environment flag", () => {
    vi.stubEnv("VITE_PLATEGAUGE_CAMERA_CANDIDATE", "1");
    expect(() => createConfig({ command: "build", mode: "production" })).toThrow(/explicit camera-candidate/);
  });
  it("requires static building rather than a candidate-mode development server", () => {
    expect(() => createConfig({ command: "serve", mode: "camera-candidate" })).toThrow(/Build the camera candidate first/);
  });
  it("cannot bundle a test model", () => {
    vi.stubEnv("VITE_SOURCE_URL", source);
    vi.stubEnv("VITE_PLATEGAUGE_TEST_MODEL", "1");
    expect(() => createConfig({ command: "build", mode: "camera-candidate" })).toThrow(/test model/);
  });
  it.each(["production", "camera-candidate"])("rejects a test adapter supplied only by a %s environment file", (mode) => {
    const fixture = mkdtempSync(join(tmpdir(), "plategauge-build-env-"));
    try {
      writeFileSync(join(fixture, `.env.${mode}`), `VITE_PLATEGAUGE_TEST_MODEL=enabled\nVITE_SOURCE_URL=${source}\n`);
      const resolved = loadEnv(mode, fixture, "VITE_");
      expect(resolved.VITE_PLATEGAUGE_TEST_MODEL).toBe("enabled");
      vi.mocked(loadEnv).mockReturnValue(resolved);
      expect(() => createConfig({ command: "build", mode })).toThrow(/test model/);
    } finally { rmSync(fixture, { recursive: true, force: true }); }
  });
  it.each(["", "https://github.com/aldaqrouqtaysir/plategauge/tree/main", "https://example.com/tree/a8c95adaa3a8f803d4e375330dde42e4706c6dee", `${source}?token=hidden`, `https://secret@github.com/aldaqrouqtaysir/plategauge/tree/a8c95adaa3a8f803d4e375330dde42e4706c6dee`])("rejects unbound or unsafe source metadata: %s", (value) => {
    vi.stubEnv("VITE_SOURCE_URL", value);
    expect(() => createConfig({ command: "build", mode: "camera-candidate" })).toThrow();
  });
});
