import { defineConfig, devices } from "@playwright/test";

const productionPort = process.env.PLATEGAUGE_PRODUCTION_PORT ?? "4175";
const productionBaseUrl = `http://127.0.0.1:${productionPort}/plategauge/`;

export default defineConfig({
  testDir: "./tests/production-release",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 90_000 },
  reporter: [["list"]],
  use: {
    baseURL: productionBaseUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `pnpm preview --host 127.0.0.1 --port ${productionPort}`,
    url: productionBaseUrl,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [{ name: "chromium-production-release", use: { ...devices["Desktop Chrome"] } }],
});
