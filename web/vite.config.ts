import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";

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
  if (mode === "production" && process.env.VITE_PLATEGAUGE_TEST_MODEL) {
    throw new Error("The test model must never be enabled in a production build.");
  }
  if (command === "build" && mode === "integration") {
    throw new Error("The integration ONNX fixture may only be served by the test dev server.");
  }
  if (command === "build" && mode === "production") {
    const sourceUrl = process.env.VITE_SOURCE_URL;
    if (!sourceUrl) {
      throw new Error("VITE_SOURCE_URL is required for a production build.");
    }
    const parsedSourceUrl = new URL(sourceUrl);
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
    base:
      process.env.VITE_BASE_PATH ??
      (mode === "test" || mode === "integration" ? "/" : "/plategauge/"),
    plugins: [react(), integrationModelFixturePlugin(mode)],
    resolve: {
      conditions: ["onnxruntime-web-use-extern-wasm", "module", "browser", mode],
    },
    build: {
      target: "es2022",
      sourcemap: mode !== "production",
    },
    worker: {
      format: "es",
    },
    test: {
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
