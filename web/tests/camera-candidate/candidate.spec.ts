import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  BASE, MODEL_SHA256, MODEL_VERSION, cropHashes, expectInert, expectPrivate,
  resumeSession, saveSession, setup, takeBefore, takePair, type AuditWindow, type SessionFile,
} from "./support";

test("capture-first home is inert, keyboard navigable and accessible at phone width", async ({ page, context, baseURL }, testInfo) => {
  const { network } = await setup(page, context, baseURL, "");
  await page.setViewportSize({ width: 320, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByTestId("capture-home")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your plate. Before and after.", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Start a capture", exact: true })).toHaveAttribute("href", `${BASE}?capture=1`);
  await expect(page.getByRole("link", { name: "Evidence", exact: true })).toHaveAttribute("href", `${BASE}?view=evidence`);
  await expect(page.locator('video,input[type="file"]')).toHaveCount(0);
  await expect(page.getByTestId("capture-home")).toContainText(/experimental/i);
  await expect(page.getByTestId("capture-home")).toContainText(/unvalidated|not validated/i);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await expectInert(page, network);
  await page.screenshot({ path: testInfo.outputPath("generated-home-320.png"), fullPage: true });
  const about = page.getByRole("link", { name: "About", exact: true });
  await about.focus(); await page.keyboard.press("Enter");
  await expect(page.locator("#about").getByRole("heading").first()).toBeInViewport();
  const capture = page.getByRole("link", { name: "Start a capture", exact: true });
  await capture.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Start with a full view.", exact: true })).toBeVisible();
  await expectInert(page, network);
});

test("secure-context capture requests video only after an explicit action and recovers from denied permission", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  await expectInert(page, network);
  expect(await page.evaluate(() => isSecureContext)).toBe(true);
  await page.evaluate(() => { (window as unknown as AuditWindow).candidateAudit.behavior = "denied"; });
  const open = page.getByRole("button", { name: "Open camera", exact: true });
  await open.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("alert")).toContainText(/permission|denied|blocked/i);
  await expect(open).toBeEnabled();
  expect(await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.requests.length)).toBe(1);
  await page.evaluate(() => { (window as unknown as AuditWindow).candidateAudit.behavior = "success"; });
  await takeBefore(page);
  const requests = await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.requests);
  expect(requests).toHaveLength(2);
  for (const request of requests) expect(request.audio).toBe(false);
  expect(requests[1]?.video).toMatchObject({ facingMode: { ideal: "environment" } });
  await expectPrivate(page, network);
});

test("cancelling a pending permission grant disposes the late stream without capturing", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  await page.evaluate(() => { (window as unknown as AuditWindow).candidateAudit.behavior = "pending"; });
  await page.getByRole("button", { name: "Open camera", exact: true }).click();
  await page.getByRole("button", { name: "Cancel camera request", exact: true }).click();
  await page.evaluate(() => { (window as unknown as AuditWindow).candidateAudit.resolvePending(); });
  await expect.poll(() => page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.tracks.filter((track) => track.ended).length)).toBe(1);
  await expect(page.getByRole("img", { name: "Your before photo", exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.frames)).toBe(0);
  await expectPrivate(page, network);
});

test("explicit paired estimate uses the pinned model and crop while retaining experimental claim boundaries", async ({ page, context, baseURL }, testInfo) => {
  const { network } = await setup(page, context, baseURL);
  await takePair(page);
  const hashes = await cropHashes(page);
  expect(hashes[0]).not.toBe(hashes[1]);
  expect(network.assets.filter((path) => /\/models\/|\/ort\//.test(path))).toEqual([]);
  const mass = page.getByRole("textbox", { name: "Starting food mass (g, optional)", exact: true });
  const estimate = page.getByRole("button", { name: "Estimate remaining", exact: true });
  for (const value of ["0", "-1", "NaN", "100001", "1e3"]) {
    await mass.fill(value); await expect(mass).toHaveAttribute("aria-invalid", "true"); await expect(estimate).toBeDisabled();
  }
  await mass.fill("");
  await estimate.focus(); await page.keyboard.press("Enter");
  const result = page.getByTestId("experimental-estimate-result");
  await expect(result).toBeVisible(); await expect(result).toBeFocused();
  await expect(result).toHaveAttribute("data-model-version", MODEL_VERSION);
  const fraction = Number(await result.getAttribute("data-leftover-fraction"));
  expect(Number.isFinite(fraction)).toBe(true); expect(fraction).toBeGreaterThanOrEqual(0); expect(fraction).toBeLessThanOrEqual(1);
  await expect(result).not.toHaveAttribute("data-remaining-mass-g");
  await expect(result).toContainText(/unvalidated/i);
  await expect(result).not.toContainText(/empirical 90%|confidence interval|synthetic test cycle/i);
  await network.settle(); expect(network.modelHashes).toContain(MODEL_SHA256);
  expect(network.assets).toContain(`${BASE}ort/ort-wasm-simd-threaded.wasm`);
  await mass.fill("250.5"); await expect(result).toHaveCount(0);
  await estimate.click(); await expect(result).toBeVisible();
  expect(Number(await result.getAttribute("data-remaining-mass-g"))).toBeCloseTo(Number(await result.getAttribute("data-leftover-fraction")) * 250.5, 10);
  await expect(page.getByTestId("experimental-estimate-mass")).toContainText(/not measured from the photos/i);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("generated-estimate-desktop.png"), fullPage: true });
  await page.getByRole("button", { name: "Retake after", exact: true }).click();
  await expect(result).toHaveCount(0);
  await page.getByRole("button", { name: "Clear photos", exact: true }).click();
  const audit = await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit);
  expect([...new Set(audit.revokedUrls)].sort()).toEqual([...new Set(audit.createdUrls)].sort());
  expect(audit.workerStops).toBeGreaterThanOrEqual(audit.workerStarts);
  await expectPrivate(page, network);
});

test("cancelling model loading terminates work and never shows a stale estimate", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  let release!: () => void;
  const held = new Promise<void>((resolveRequest) => { release = resolveRequest; });
  let requested = false;
  await context.route(`**${BASE}models/plategauge.onnx`, async (route) => {
    expect(route.request().method()).toBe("GET"); expect(route.request().postDataBuffer()).toBeNull();
    requested = true; await held;
    await route.abort("aborted").catch(() => undefined);
  });
  await takePair(page);
  await page.getByRole("button", { name: "Estimate remaining", exact: true }).click();
  await expect.poll(() => requested).toBe(true);
  await page.getByRole("button", { name: "Cancel estimate", exact: true }).click();
  await expect(page.getByRole("button", { name: "Estimate remaining", exact: true })).toBeFocused();
  release();
  await expect.poll(() => page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.workerStops)).toBeGreaterThan(0);
  await expect(page.getByTestId("experimental-estimate-result")).toHaveCount(0);
  await expect(page.getByRole("img", { name: "Your before photo for review", exact: true })).toBeVisible();
  await expectPrivate(page, network);
});

test("manual before-only save and resume survives reload but does not auto-open camera or estimate", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  await expect(page.getByRole("button", { name: "Save session", exact: true })).toBeDisabled();
  await takeBefore(page);
  const saved = await saveSession(page);
  const record = JSON.parse(saved.buffer.toString("utf8")) as Record<string, unknown>;
  expect(record.format).toBe("plategauge-session"); expect(record.version).toBe(1); expect(record.after).toBeNull();
  expect(Object.keys(record).sort()).toEqual(["format", "version", "compatibility", "before", "after", "startingMass", "checksum"].sort());
  await page.reload(); await resumeSession(page, saved);
  await expect(page.getByRole("img", { name: "Before photo reference", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Review & estimate", exact: true })).toBeDisabled();
  await expectInert(page, network);
  await page.getByRole("button", { name: "Clear photos", exact: true }).click();
  await expect(page.getByRole("img", { name: "Before photo reference", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("session-controls")).toContainText(/delet/i);
  await resumeSession(page, saved); // Clearing RAM cannot delete the downloaded bytes.
  await expect(page.getByRole("img", { name: "Before photo reference", exact: true })).toBeVisible();
  await expectInert(page, network);
});

test("pair resume preserves exact crops and mass and replacement requires explicit consent", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  await takePair(page);
  const mass = page.getByRole("textbox", { name: "Starting food mass (g, optional)", exact: true });
  await mass.fill("400"); const originalCrops = await cropHashes(page); const saved = await saveSession(page);
  await page.reload(); await resumeSession(page, saved);
  await expect(mass).toHaveValue("400"); expect(await cropHashes(page)).toEqual(originalCrops); await expectInert(page, network);
  await mass.fill("375"); await resumeSession(page, saved);
  const confirmation = page.getByTestId("session-replace-confirmation");
  await expect(confirmation).toBeVisible(); await expect(mass).toHaveValue("375");
  const keep = page.getByRole("button", { name: "Keep current session", exact: true });
  await expect(keep).toBeFocused(); await keep.click();
  await expect(confirmation).toHaveCount(0); await expect(mass).toHaveValue("375");
  await resumeSession(page, saved); await expect(confirmation).toBeVisible();
  await page.getByRole("button", { name: "Replace current session", exact: true }).click();
  await expect(confirmation).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Review the pair. Then estimate.", exact: true })).toBeFocused();
  await expect(mass).toHaveValue("400"); expect(await cropHashes(page)).toEqual(originalCrops);
  await expectInert(page, network);
});

test("malformed, oversized and unsupported imports preserve the existing session without execution", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  await takePair(page);
  const mass = page.getByRole("textbox", { name: "Starting food mass (g, optional)", exact: true });
  await mass.fill("325"); const originalCrops = await cropHashes(page); const saved = await saveSession(page);
  const version = JSON.parse(saved.buffer.toString("utf8")) as Record<string, unknown>; version.version = 999;
  const checksum = JSON.parse(saved.buffer.toString("utf8")) as Record<string, unknown>; checksum.checksum = "0".repeat(64);
  const bad: SessionFile[] = [
    { ...saved, buffer: saved.buffer.subarray(0, 25) },
    { ...saved, buffer: Buffer.alloc(15 * 1024 * 1024 + 1, 32) },
    { ...saved, buffer: Buffer.from(JSON.stringify(version)) },
    { ...saved, buffer: Buffer.from(JSON.stringify(checksum)) },
    { name: "private-name.svg", mimeType: "image/svg+xml", buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>') },
  ];
  const dialogs: string[] = [];
  page.on("dialog", (dialog) => { dialogs.push(dialog.type()); void dialog.dismiss(); });
  for (const file of bad) {
    await resumeSession(page, file);
    await expect(page.getByTestId("session-error")).toBeVisible();
    await expect(page.getByTestId("session-error")).not.toContainText("private-name");
    await expect(page.getByTestId("session-replace-confirmation")).toHaveCount(0);
    await expect(mass).toHaveValue("325"); expect(await cropHashes(page)).toEqual(originalCrops);
  }
  expect(dialogs).toEqual([]);
  expect(await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.workerStarts)).toBe(0);
  await expectPrivate(page, network);
});

test("evidence navigation releases camera and photos and ambiguous queries never activate capture", async ({ page, context, baseURL }) => {
  const { network, lifecycle } = await setup(page, context, baseURL);
  await takeBefore(page); await page.getByRole("button", { name: "Continue to after", exact: true }).click();
  await page.getByRole("button", { name: "Open camera", exact: true }).click();
  await expect(page.getByRole("button", { name: "Take after photo", exact: true })).toBeEnabled();
  const beforeStops = lifecycle.stopped.length;
  await page.getByRole("link", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("banner")).toHaveCount(1);
  await expect(page.getByRole("complementary", { name: "About these results", exact: true })).toContainText("not validation of camera estimates");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await expect(page.getByTestId("camera-capture")).toHaveCount(0);
  await expect.poll(() => lifecycle.stopped.length).toBeGreaterThan(beforeStops);
  await expect.poll(() => [...new Set(lifecycle.revoked)].sort()).toEqual([...new Set(lifecycle.created)].sort());
  for (const query of ["?unknown=1", "?capture=1&view=evidence", "?capture=1&capture=1"]) {
    await page.goto(`${BASE}${query}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByTestId("camera-capture")).toHaveCount(0);
    await expect(page.getByTestId("capture-home")).toBeVisible();
    await expectPrivate(page, network);
    expect(await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.requests.length)).toBe(0);
  }
});

test("phone session controls and device-check export are keyboard accessible and retain no personal outputs", async ({ page, context, baseURL }, testInfo) => {
  const { network } = await setup(page, context, baseURL);
  await page.setViewportSize({ width: 320, height: 844 }); await page.emulateMedia({ reducedMotion: "reduce" });
  await takeBefore(page);
  await expect(page.getByTestId("session-controls")).toContainText(/unencrypted/i);
  const saved = await saveSession(page, true); await resumeSession(page, saved, true);
  await expect(page.getByTestId("session-replace-confirmation")).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  const keep = page.getByRole("button", { name: "Keep current session", exact: true });
  await expect(keep).toBeFocused(); await page.keyboard.press("Enter");
  await expect(page.getByTestId("session-replace-confirmation")).toHaveCount(0);
  const device = page.locator(".rc-device-check"); await device.locator("summary").click();
  const outcomes = device.locator("fieldset select"); await expect(outcomes).toHaveCount(7);
  for (let index = 0; index < 7; index++) await expect(outcomes.nth(index)).toHaveValue("untested");
  const downloading = page.waitForEvent("download");
  const button = device.getByRole("button", { name: "Download device check", exact: true });
  await button.focus(); await page.keyboard.press("Enter");
  const file = await downloading; expect(await file.failure()).toBeNull();
  const stream = await file.createReadStream();
  if (!stream) throw new Error("Generated diagnostic export unavailable.");
  const chunks: Buffer[] = []; for await (const chunk of stream) chunks.push(Buffer.from(chunk as Uint8Array));
  const text = Buffer.concat(chunks).toString("utf8");
  const report = JSON.parse(text) as Record<string, unknown>;
  expect(report.releaseApproval).toBe(false); expect(report.accuracyValidation).toBe(false);
  expect(text).not.toMatch(/previewJpegBase64|cropRgbaBase64|startingMass|leftoverFraction|remainingMassG|data:image/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("generated-session-device-320.png"), fullPage: true });
  await expectPrivate(page, network);
});
