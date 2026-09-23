import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { loadEnv, type Plugin } from "vite";

function integrationModelFixturePlugin(mode: string): Plugin {
  return {
    name: "plategauge-integration-model-fixture",
    apply: "serve",
    configureServer(server) {
      if (mode !== "integration") return;

      const fixtureDirectory = fileURLToPath(
        new URL("./tests/fixtures/production-model/", import.meta.url),
      );
      const manifest = readFileSync(`${fixtureDirectory}/release.json`);
      const encodedModel = readFileSync(`${fixtureDirectory}/plategauge.onnx.base64`, "utf8").trim();
      const model = Buffer.from(encodedModel, "base64");

      server.middlewares.use((request, response, next) => {
        const pathname = (request.url ?? "").split("?", 1)[0];
        if (pathname === "/models/release.json") {
          response.statusCode = 200;
          response.setHeader("Content-Type", "application/json; charset=utf-8");
          response.setHeader("Cache-Control", "no-store");
          response.end(manifest);
          return;
        }
        if (pathname === "/models/plategauge.onnx") {
          response.statusCode = 200;
          response.setHeader("Content-Type", "application/octet-stream");
          response.setHeader("Cache-Control", "no-store");
          response.end(model);
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig(({ command, mode }) => {
  const environment = loadEnv(mode, fileURLToPath(new URL(".", import.meta.url)), "VITE_");
  const cameraCandidate = mode === "camera-candidate";
  if (environment.VITE_PLATEGAUGE_CAMERA_CANDIDATE) {
    throw new Error("The camera capability is selected only by the explicit camera-candidate build mode.");
  }
  if (cameraCandidate && command !== "build") {
    throw new Error("Build the camera candidate first, then preview its static output.");
  }
  if ((mode === "production" || cameraCandidate) && environment.VITE_PLATEGAUGE_TEST_MODEL) {
    throw new Error("The test model must never be enabled in a production build.");
  }
  if (command === "build" && mode === "integration") {
    throw new Error("The integration ONNX fixture may only be served by the test dev server.");
  }
  if (command === "build" && (mode === "production" || cameraCandidate)) {
    const sourceUrl = environment.VITE_SOURCE_URL;
    if (!sourceUrl) {
      throw new Error("VITE_SOURCE_URL is required for a production build.");
    }
    const parsedSourceUrl = new URL(sourceUrl);
    if (cameraCandidate && (parsedSourceUrl.origin !== "https://github.com"
      || !/^\/aldaqrouqtaysir\/plategauge\/tree\/[a-f0-9]{40}$/.test(parsedSourceUrl.pathname))) {
      throw new Error("The camera candidate requires the exact source-commit GitHub URL.");
    }
    if (
      parsedSourceUrl.protocol !== "https:" ||
      parsedSourceUrl.username ||
      parsedSourceUrl.password ||
      parsedSourceUrl.search ||
      parsedSourceUrl.hash
    ) {
      throw new Error("VITE_SOURCE_URL must be a credential-free HTTPS repository URL.");
    }
  }

  return {
    define: {
      "import.meta.env.VITE_PLATEGAUGE_CAMERA_CANDIDATE": JSON.stringify(cameraCandidate ? "1" : "0"),
      ...((mode === "production" || cameraCandidate) ? { "import.meta.env.VITE_PLATEGAUGE_TEST_MODEL": JSON.stringify("") } : {}),
    },
    base:
      environment.VITE_BASE_PATH ??
      (mode === "test" || mode === "integration" ? "/" : "/plategauge/"),
    plugins: [react(), integrationModelFixturePlugin(mode), ...(cameraCandidate ? [{
      name: "explicit-camera-candidate-entry",
      generateBundle() {
        for (const [source, destination] of [
          ["../docs/CAMERA_PRIVACY_NOTICE.md", "legal/CAMERA_PRIVACY_NOTICE.md"],
          ["../docs/CAMERA_SYSTEM_CARD.md", "legal/CAMERA_SYSTEM_CARD.md"],
          ["./src/libv2/PILLOW_RESAMPLING_NOTICE.md", "legal/PILLOW_RESAMPLING_NOTICE.md"],
        ] as const) {
          this.emitFile({ type: "asset", fileName: destination, source: readFileSync(fileURLToPath(new URL(source, import.meta.url))) });
        }
      },
      transformIndexHtml: {
        order: "pre" as const,
        handler(html: string) {
          const entry = '<script type="module" src="/src/main.tsx"></script>';
          if (html.split(entry).length !== 2) throw new Error("Expected one benchmark entry; refuse an ambiguous candidate build.");
          return html.replace(entry, '<script type="module" src="/src/candidate/main.tsx"></script>')
            .replace("PlateGauge · Benchmark &amp; failure explorer", "PlateGauge · Experimental camera")
            .replace("PlateGauge is a transparent benchmark and failure explorer for a category-shift leftover-fraction computer-vision study.", "Capture a before-and-after pair and explore an experimental, on-device food-leftover estimate. Not a scale or a validated measurement.")
            .replace("object-src 'none';", "media-src 'self' blob:; frame-src 'none'; object-src 'none';");
        },
      },
    } satisfies Plugin] : [])],
    resolve: {
      conditions: ["onnxruntime-web-use-extern-wasm", "module", "browser", mode],
    },
    build: {
      outDir: cameraCandidate ? "dist-camera" : "dist",
      target: "es2022",
      sourcemap: mode !== "production" && !cameraCandidate,
    },
    worker: {
      format: "es",
    },
    test: {
      maxWorkers: 2,
      // Coverage-instrumented pixel fixtures exceed Vitest's default 5s on
      // constrained hosts. Runtime deadline behavior is tested with fake clocks;
      // this runner budget is not an inference/capture performance threshold.
      testTimeout: 15_000,
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      include: ["src/**/*.test.ts", "tests/unit/**/*.test.ts"],
      coverage: {
        provider: "v8",
        reporter: ["text", "html"],
        include: [
          "src/lib/imageValidation.ts",
          "src/lib/preprocess.ts",
          "src/lib/releaseManifest.ts",
          "src/lib/result.ts",
          "src/lib/testModel.ts",
          "src/capturePrototype/operations.ts",
          "src/captureCamera/*.{ts,tsx}",
          "src/experimentalEstimator/*.ts",
          "src/libv2/*.ts",
          "src/candidate/policy.ts",
        ],
        thresholds: {
          lines: 85,
          statements: 85,
          functions: 85,
          branches: 80,
        },
      },
    },
  };
});
