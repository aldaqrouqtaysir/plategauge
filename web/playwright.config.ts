import { defineConfig, devices } from "@playwright/test";

const e2ePort = process.env.PLATEGAUGE_E2E_PORT ?? "4173";
const e2eBaseUrl = `http://127.0.0.1:${e2ePort}`;

export default defineConfig({
  testDir: "./tests/e2e",
  // Image decoding and WebKit canvas work can become timing-sensitive when all
  // abuse/resize cases run concurrently on a small CI host. Serial execution
  // keeps this release gate deterministic without weakening any assertion.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: e2eBaseUrl,
    trace: "on-first-retry",
  },
  webServer: {
    command: `pnpm dev --mode test --host 127.0.0.1 --port ${e2ePort}`,
    url: e2eBaseUrl,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
