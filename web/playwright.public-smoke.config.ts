import { defineConfig, devices } from "@playwright/test";

function requirePublicUrl(): string {
  const raw = process.env.PLATEGAUGE_PUBLIC_URL?.trim();
  if (!raw) {
    throw new Error(
      "PLATEGAUGE_PUBLIC_URL is required for the public smoke test; refusing to use a local or synthetic fallback.",
    );
  }

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("PLATEGAUGE_PUBLIC_URL must be a valid absolute HTTPS URL.");
  }
  if (url.protocol !== "https:") {
    throw new Error("PLATEGAUGE_PUBLIC_URL must use HTTPS.");
  }
  url.search = "";
  url.hash = "";
  if (!url.pathname.endsWith("/")) url.pathname += "/";
  return url.toString();
}

export default defineConfig({
  testDir: "./tests/public-smoke",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 1,
  timeout: 120_000,
  expect: { timeout: 90_000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results/public-smoke-report.json" }],
  ],
  use: {
    baseURL: requirePublicUrl(),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium-public-release", use: { ...devices["Desktop Chrome"] } }],
});
