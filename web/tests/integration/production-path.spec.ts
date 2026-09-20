import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const manifestPath = fileURLToPath(
  new URL("../fixtures/production-model/release.json", import.meta.url),
);

test("rejects an ONNX fixture whose bytes do not match the release checksum", async ({ page }) => {
  const validManifest = readFileSync(manifestPath, "utf8");
  const invalidManifest = validManifest.replace(
    /"modelSha256": "[a-f0-9]{64}"/,
    `"modelSha256": "${"0".repeat(64)}"`,
  );
  await page.route("**/models/release.json", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: invalidManifest }),
  );

  await page.goto("/?benchmark=1");
  await expect(page.getByRole("alert")).toContainText("checksum", { timeout: 30_000 });
  await expect(page.getByTestId("model-ready")).toHaveCount(0);
});

test("runs fixed-pair preprocessing and two-input ONNX inference without rendering a prediction", async ({
  page,
}) => {
  await page.goto("/?benchmark=1");
  await expect(page.getByTestId("model-ready")).toContainText(
    "integration-fixture/v1-not-for-release",
    { timeout: 30_000 },
  );
  await expect(page.getByTestId("fixed-example-ready")).toContainText("lefood-0192 ready");
  await expect(page.getByText("Test adapter active.")).toHaveCount(0);

  const requestsAfterReady: string[] = [];
  page.on("request", (request) => {
    const protocol = new URL(request.url()).protocol;
    if (protocol === "http:" || protocol === "https:") {
      requestsAfterReady.push(`${request.method()} ${request.url()}`);
    }
  });

  await page.getByTestId("run-fixed-example").click();
  const output = page.getByTestId("runtime-output");
  await expect(output).toContainText("Fixed worker cycle complete");
  await expect(output).toContainText(/\d+ ms/);
  await expect(output).toContainText("No numeric model output is rendered");
  await expect(output).not.toContainText(/%/);
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await expect(page.getByText(/Empirical 90% interval/i)).toHaveCount(0);
  expect(requestsAfterReady).toEqual([]);
});
