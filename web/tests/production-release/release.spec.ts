import { expect, test } from "@playwright/test";

const expectedSourceUrl =
  process.env.PLATEGAUGE_EXPECTED_SOURCE_URL ??
  "https://github.com/aldaqrouqtaysir/plategauge";
const forbiddenReleaseStatePhrases = [
  "not released",
  "pending gate d",
  "planned for github pages",
  "no public url",
];

const allowedStaticPath = /^\/plategauge\/(?:$|assets\/(?:index|model\.worker)-[A-Za-z0-9_-]+\.(?:css|js)$|evidence\/benchmark-evidence\.json$|examples\/lefood-(?:0142|0192|0226|0320|0400|0441|0461|0489|0507|0530)-(?:before|after)\.jpg$|models\/(?:release\.json|plategauge\.onnx)$|ort\/ort-wasm-simd-threaded\.(?:mjs|wasm)$)$/;

test("serves the built fixed-example release using only allowlisted same-origin requests", async ({
  page,
  baseURL,
}) => {
  if (!baseURL) throw new Error("Production smoke baseURL is unavailable.");
  const expectedOrigin = new URL(baseURL).origin;
  const observed: string[] = [];
  const violations: string[] = [];

  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.protocol !== "http:" && url.protocol !== "https:") return;
    observed.push(`${request.method()} ${url.pathname}`);
    if (
      request.method() !== "GET" ||
      url.origin !== expectedOrigin ||
      !allowedStaticPath.test(url.pathname)
    ) {
      violations.push(`${request.method()} ${request.url()}`);
    }
  });

  await page.goto("./?benchmark=1", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("PlateGauge v1.0.2 · benchmark and failure explorer")).toBeVisible();
  await expect(page.getByText(/benchmark-only category-shift/i)).toBeVisible();
  await expect(page.getByTestId("model-ready")).toContainText("Frozen model ready.");
  await expect(page.getByTestId("fixed-example-ready")).toContainText("lefood-0192 ready");
  await page.getByTestId("run-fixed-example").click();

  const output = page.getByTestId("runtime-output");
  await expect(output).toContainText("Fixed worker cycle complete");
  await expect(output).toContainText("No numeric model output is rendered");
  await expect(output).not.toContainText(/%/);
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await expect(page.getByText(/Empirical 90% interval/i)).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Release notices/i })).toHaveAttribute(
    "href",
    "/plategauge/legal/NOTICE.txt",
  );
  await expect(page.locator(".footer-disclosure")).toHaveCount(0);
  await expect(page.getByText(/Substantially AI-assisted/i)).toHaveCount(0);
  await expect(page.getByText(/accepts no uploads and sends no inference API requests/i)).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Privacy", exact: true })).toHaveAttribute(
    "href", "/plategauge/legal/PRIVACY_NOTICE.md",
  );
  await expect(page.getByRole("link", { name: "AI-assistance disclosure", exact: true })).toHaveAttribute(
    "href", "/plategauge/legal/AI_ASSISTANCE_LOG.md",
  );
  await expect(page.getByRole("link", { name: "Notices", exact: true })).toHaveAttribute(
    "href",
    "/plategauge/legal/NOTICE.txt",
  );
  await expect(page.getByRole("link", { name: "Dependency licenses" })).toHaveAttribute(
    "href",
    "/plategauge/legal/THIRD_PARTY_LICENSES.json",
  );
  await expect(page.getByRole("link", { name: "Source", exact: true })).toHaveAttribute(
    "href",
    expectedSourceUrl,
  );
  const visibleText = (await page.locator("body").innerText()).toLowerCase();
  for (const phrase of forbiddenReleaseStatePhrases) {
    expect(visibleText).not.toContain(phrase);
  }

  expect(observed.some((entry) => entry.endsWith("/models/plategauge.onnx"))).toBe(true);
  expect(observed.some((entry) => entry.endsWith("/ort/ort-wasm-simd-threaded.wasm"))).toBe(
    true,
  );
  expect(violations).toEqual([]);
});

test("ships self-contained project, dataset, model, and dependency notices", async ({
  request,
}) => {
  const notice = await request.get("./legal/NOTICE.txt");
  expect(notice.ok()).toBe(true);
  const noticeText = await notice.text();
  expect(noticeText).toContain("LeFood-Set v1");
  expect(noticeText).toContain("CC BY 4.0");
  expect(noticeText).toContain("9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675");

  const license = await request.get("./legal/LICENSE.txt");
  expect(license.ok()).toBe(true);
  expect(await license.text()).toContain("Apache License");

  const dependencies = await request.get("./legal/THIRD_PARTY_LICENSES.json");
  expect(dependencies.ok()).toBe(true);
  const inventory = (await dependencies.json()) as Record<string, unknown>;
  expect(Object.keys(inventory).sort()).toEqual(["Apache-2.0", "BSD-3-Clause", "ISC", "MIT"]);

  const privacy = await request.get("./legal/PRIVACY_NOTICE.md");
  expect(privacy.ok()).toBe(true);
  const privacyText = await privacy.text();
  expect(privacyText).toContain("ordinary request metadata");
  for (const phrase of forbiddenReleaseStatePhrases) {
    expect(privacyText.toLowerCase()).not.toContain(phrase);
  }

  const assistance = await request.get("./legal/AI_ASSISTANCE_LOG.md");
  expect(assistance.ok()).toBe(true);
  expect(await assistance.text()).toContain("AI-assistance disclosure");

  const evidence = await request.get("./evidence/benchmark-evidence.json");
  expect(evidence.ok()).toBe(true);
  const evidencePayload = (await evidence.json()) as {
    workloadEvidence: { records: unknown[] };
    categoryComparisons: unknown[];
    robustnessSummary: { downgradeRequired: boolean };
  };
  expect(evidencePayload.workloadEvidence.records).toHaveLength(8);
  expect(evidencePayload.categoryComparisons).toHaveLength(34);
  expect(evidencePayload.robustnessSummary.downgradeRequired).toBe(true);
});
