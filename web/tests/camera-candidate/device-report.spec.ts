import { expect, test, type Page } from "@playwright/test";
import { setup, expectInert, expectPrivate, type AuditWindow, type NetworkAudit } from "./support";

const labels = [
  "Camera permission denial and retry", "Live guide and model-input review",
  "Estimate starts only when requested", "Cancel and retake stop stale work",
  "Save, reload and resume your own session", "Hide or lock, then return to the page",
  "Clear removes photos from this page",
];
const checkKeys = ["permissionRecovery", "framingReview", "explicitEstimate", "cancelRetake", "sessionResume", "hiddenReturn", "clearCleanup"];
type Report = {
  schemaVersion: string; purpose: string; releaseApproval: boolean; accuracyValidation: boolean;
  setup: { device: string; browser: string; browserVersion: string | null; environment: string };
  checks: Record<string, string>; reviewStatus: string;
  currentPage: { cameraReady: boolean; beforePresent: boolean; afterPresent: boolean };
  latestTimingMs: { capturePreparation: number | null; estimateClickToResult: number | null; modelProcessing: number | null };
  timingScope: string; peakMemoryMeasured: boolean; limitations: string[];
};

/** Read the real browser download, not a mocked click or constructed report. */
async function exportReport(page: Page): Promise<Report> {
  await page.evaluate(() => {
    const target = window as unknown as Window & { exportedMimeTypes: string[] };
    target.exportedMimeTypes = [];
    const create = URL.createObjectURL.bind(URL);
    URL.createObjectURL = (blob) => {
      target.exportedMimeTypes.push(blob instanceof Blob ? blob.type : "not-a-blob");
      return create(blob);
    };
  });
  const waiting = page.waitForEvent("download");
  const button = page.getByRole("button", { name: "Download device check", exact: true });
  await button.focus(); await expect(button).toBeFocused(); await page.keyboard.press("Enter");
  const download = await waiting;
  try {
    expect(download.suggestedFilename()).toBe("plategauge-device-check.json");
    const stream = await download.createReadStream();
    if (!stream) throw new Error("Report download stream unavailable");
    const chunks: Buffer[] = []; let bytes = 0;
    for await (const raw of stream) {
      const chunk = Buffer.from(raw as Uint8Array); bytes += chunk.length;
      if (bytes > 5_000) { stream.destroy(); throw new Error("Report exceeds its metadata-only budget"); }
      chunks.push(chunk);
    }
    expect(await download.failure()).toBeNull();
    expect(await page.evaluate(() => (window as unknown as { exportedMimeTypes: string[] }).exportedMimeTypes)).toEqual(["application/json"]);
    const text = Buffer.concat(chunks).toString("utf8");
    expect(text).not.toMatch(/data:image|base64|blob:|startingMass|initialMassG|leftoverFraction|remainingMassG|userAgent|deviceId/);
    const report = JSON.parse(text) as Report;
    expect(Object.keys(report).sort()).toEqual([
      "schemaVersion", "purpose", "releaseApproval", "accuracyValidation", "setup", "checks", "reviewStatus",
      "currentPage", "latestTimingMs", "timingScope", "peakMemoryMeasured", "limitations",
    ].sort());
    expect(report.schemaVersion).toBe("plategauge-device-check-v1");
    expect(report.purpose).toBe("self_reported_local_workflow_check");
    expect(report.releaseApproval).toBe(false); expect(report.accuracyValidation).toBe(false);
    expect(report.peakMemoryMeasured).toBe(false);
    expect(Object.keys(report.setup).sort()).toEqual(["browser", "browserVersion", "device", "environment"]);
    expect(Object.keys(report.checks).sort()).toEqual([...checkKeys].sort());
    expect(report.currentPage).toEqual({ cameraReady: false, beforePresent: false, afterPresent: false });
    expect(report.latestTimingMs).toEqual({ capturePreparation: null, estimateClickToResult: null, modelProcessing: null });
    expect(report.timingScope).toContain("not p50/p95");
    expect(report.limitations).toHaveLength(4);
    expect(report.limitations).toContain("Operator-selected device, browser and outcomes are not independently verified.");
    return report;
  } finally {
    await download.delete(); // Only the synthetic, temporary metadata download; never a user file.
  }
}

async function verifyIdlePrivacy(page: Page, network: NetworkAudit): Promise<void> {
  await expect(page.locator('a[download="plategauge-device-check.json"]')).toHaveCount(0);
  await expectInert(page, network);
  await expectPrivate(page, network);
  expect(network.assets.filter((path) => /\/(?:models|ort)\//.test(path))).toEqual([]);
  await expect.poll(() => page.evaluate(() => {
    const audit = (window as unknown as AuditWindow).candidateAudit;
    return [...new Set(audit.createdUrls)].every((url) => audit.revokedUrls.includes(url));
  })).toBe(true);
}

test("empty-page device report is explicitly incomplete, metadata-only and hardware-inert", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  let downloads = 0; page.on("download", () => downloads++);
  const panel = page.locator("details.rc-device-check");
  await expect(panel).not.toHaveAttribute("open");
  await verifyIdlePrivacy(page, network); expect(downloads).toBe(0);
  await panel.locator("summary").click();
  for (const label of labels) await expect(page.getByRole("combobox", { name: label, exact: true })).toHaveValue("untested");
  const record = await exportReport(page);
  expect(downloads).toBe(1);
  expect(record.reviewStatus).toBe("incomplete");
  expect(new Set(Object.values(record.checks))).toEqual(new Set(["untested"]));
  expect(record.setup).toEqual({ device: "unspecified", browser: "unspecified", browserVersion: null, environment: "unspecified" });
  await expect(panel.getByRole("status")).toContainText("not photos or estimates");
  await verifyIdlePrivacy(page, network);
});

test("invalid report version blocks download and a synthetic failure never becomes certification", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  let downloads = 0; page.on("download", () => downloads++);
  await verifyIdlePrivacy(page, network);
  await page.locator("details.rc-device-check summary").click();
  const version = page.getByRole("textbox", { name: /Browser version/ });
  await version.fill("INVALID_TEST_VERSION");
  await page.getByRole("button", { name: "Download device check", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("numeric browser version");
  expect(downloads).toBe(0);
  expect(await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.createdUrls)).toEqual([]);
  await verifyIdlePrivacy(page, network);
  await version.fill("999.0"); // Synthetic form input, not a browser or camera observation.
  await page.getByRole("combobox", { name: labels[0], exact: true }).selectOption("fail");
  const record = await exportReport(page);
  expect(record.reviewStatus).toBe("attention_needed");
  expect(record.checks.permissionRecovery).toBe("fail");
  expect(record.setup.environment).toBe("unspecified");
  expect(downloads).toBe(1);
  await verifyIdlePrivacy(page, network);
});

test("device-report reset and reload discard form data without inventing observations", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  await verifyIdlePrivacy(page, network);
  const summary = page.locator("details.rc-device-check summary");
  await summary.click();
  await page.getByRole("combobox", { name: "Device type", exact: true }).selectOption("other");
  await page.getByRole("combobox", { name: labels[2], exact: true }).selectOption("fail");
  await page.getByRole("button", { name: "Reset device check", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Device type", exact: true })).toHaveValue("unspecified");
  for (const label of labels) await expect(page.getByRole("combobox", { name: label, exact: true })).toHaveValue("untested");
  await page.getByRole("textbox", { name: /Browser version/ }).fill("999.0");
  await verifyIdlePrivacy(page, network);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("details.rc-device-check")).not.toHaveAttribute("open");
  await verifyIdlePrivacy(page, network);
  await summary.click();
  await expect(page.getByRole("textbox", { name: /Browser version/ })).toHaveValue("");
  for (const label of labels) await expect(page.getByRole("combobox", { name: label, exact: true })).toHaveValue("untested");
  const record = await exportReport(page);
  expect(record.reviewStatus).toBe("incomplete");
  expect(record.setup).toEqual({ device: "unspecified", browser: "unspecified", browserVersion: null, environment: "unspecified" });
  await verifyIdlePrivacy(page, network);
});
