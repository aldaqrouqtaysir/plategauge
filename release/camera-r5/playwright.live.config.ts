import { resolve } from "node:path";
import { defineConfig, devices } from "../../web/node_modules/@playwright/test/index.js";
import { reserveDiagnosticsDirectory, smokeConfiguration } from "./live-support";

const settings = smokeConfiguration();
const output = reserveDiagnosticsDirectory(process.env.PLATEGAUGE_CAMERA_SMOKE_ARTIFACTS, resolve(__dirname, "../.."));

/** Release operations only: no build, dev server, model substitute or camera permission. */
export default defineConfig({
  testDir: ".", testMatch: "live.spec.ts", fullyParallel: false, workers: 1,
  forbidOnly: true, retries: 0, timeout: 120_000, expect: { timeout: 75_000 },
  outputDir: resolve(output, "artifacts"),
  reporter: [["list"], ["json", { outputFile: resolve(output, "report.json") }]],
  use: {
    baseURL: settings.baseURL, serviceWorkers: "block", permissions: [],
    ignoreHTTPSErrors: false, acceptDownloads: true,
    trace: "retain-on-failure", screenshot: "only-on-failure",
  },
  projects: [{ name: "camera-" + settings.mode, use: { ...devices["Desktop Chrome"] } }],
});
