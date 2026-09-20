import { expect, test } from "@playwright/test";

test("runs one deployed fixed-pair model cycle without exposing a numeric prediction", async ({
  page,
  baseURL,
}) => {
  if (!baseURL) throw new Error("Public smoke baseURL is unavailable.");
  const root = new URL(baseURL);
  const rootPath = root.pathname.endsWith("/") ? root.pathname : `${root.pathname}/`;
  const allowedRelativePath = /^(?:$|assets\/(?:index|model\.worker)-[A-Za-z0-9_-]+\.(?:css|js)$|evidence\/benchmark-evidence\.json$|examples\/lefood-0192-(?:before|after)\.jpg$|models\/(?:release\.json|plategauge\.onnx)$|ort\/ort-wasm-simd-threaded\.(?:mjs|wasm)$)$/;
  const observed: string[] = [];
  const violations: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.protocol !== "http:" && url.protocol !== "https:") return;
    observed.push(`${request.method()} ${url.pathname}`);
    const relativePath = url.pathname.startsWith(rootPath)
      ? url.pathname.slice(rootPath.length)
      : url.pathname;
    if (
      request.method() !== "GET" ||
      url.origin !== root.origin ||
      !allowedRelativePath.test(relativePath)
    ) {
      violations.push(`${request.method()} ${request.url()}`);
    }
  });

  await page.goto("./?benchmark=1", { waitUntil: "domcontentloaded" });
  const ready = page.getByTestId("model-ready");
  await expect(ready).toContainText("Frozen model ready.");
  await expect(ready).not.toContainText("Test adapter active.");
  await expect(page.getByTestId("fixed-example-ready")).toContainText("lefood-0192 ready");

  await page.getByTestId("run-fixed-example").click();
  const output = page.getByTestId("runtime-output");
  await expect(output).toContainText("Fixed worker cycle complete");
  await expect(output).toContainText("No numeric model output is rendered");
  await expect(output).not.toContainText(/%/);
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await expect(page.getByText(/Empirical 90% interval/i)).toHaveCount(0);
  expect(observed.some((entry) => entry.endsWith("/models/plategauge.onnx"))).toBe(true);
  expect(violations).toEqual([]);
});
