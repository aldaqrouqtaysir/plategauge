import { defineConfig, devices } from "@playwright/test";

const baseURL = "http://127.0.0.1:4198/plategauge/";
const firefoxExecutable = process.env.PLATEGAUGE_FIREFOX_EXECUTABLE;

/** Exercises only an already-built candidate; no dev server or test model. */
export default defineConfig({
  testDir: "./tests/camera-candidate",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 30_000 },
  reporter: [["list"]],
  outputDir: process.env.PLATEGAUGE_CAMERA_CANDIDATE_ARTIFACTS ?? "test-results/camera-candidate",
  use: { baseURL, trace: "retain-on-failure", screenshot: "only-on-failure", serviceWorkers: "block" },
  webServer: {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js preview --outDir dist-camera --host 127.0.0.1 --port 4198 --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"], ...(firefoxExecutable ? { launchOptions: { executablePath: firefoxExecutable } } : {}) } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
