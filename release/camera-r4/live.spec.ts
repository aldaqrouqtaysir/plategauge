import { expect, test } from "../../web/node_modules/@playwright/test/index.js";
import {
  cropHashes, expectInert, expectPrivate, resumeSession, saveSession, takeBefore, type AuditWindow,
} from "../../web/tests/camera-candidate/support";
import {
  BASE, MODEL_SHA256, MODEL_VERSION, SOURCE_URL, armGeneratedCamera,
  assetForUrl, expectRetiredResourceUnavailable, generatedPair, parseInventory,
  requireGeneratedCamera, reserveDiagnosticsDirectory, setupLive, smokeConfiguration,
} from "./live-support";

test("preflight rejects unsafe inventories, destinations and implicit modes", () => {
  const settings = smokeConfiguration();
  expect(parseInventory(settings.inventory).files).toHaveLength(45);
  expect(() => parseInventory({ ...settings.inventory, basePath: BASE })).toThrow();
  expect(() => parseInventory({ ...settings.inventory, appSourceCommit: "0".repeat(40) })).toThrow();
  expect(() => parseInventory({ ...settings.inventory, files: [...settings.inventory.files].reverse() })).toThrow();
  for (const replacement of [
    { path: "../outside", size: 1, sha256: "0".repeat(64) },
    { ...settings.inventory.files[0], size: Infinity },
    { ...settings.inventory.files[0], sha256: "0".repeat(63) },
  ]) {
    expect(() => parseInventory({ ...settings.inventory, files: [replacement, ...settings.inventory.files.slice(1)] })).toThrow();
  }
  const changedModel = settings.inventory.files.map((entry) => entry.path === "models/plategauge.onnx"
    ? { ...entry, sha256: "0".repeat(64) } : entry);
  expect(() => parseInventory({ ...settings.inventory, files: changedModel })).toThrow();
  const retired = settings.inventory.files.map((entry, index) => index === 0
    ? { ...entry, path: "legal/AI_ASSISTANCE_LOG.md" } : entry).sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
  expect(() => parseInventory({ ...settings.inventory, files: retired })).toThrow();
  expect(assetForUrl(settings.baseURL + "?capture=1", settings.baseURL, settings.inventory)?.path).toBe("index.html");
  for (const target of [
    "https://example.invalid/plategauge/", settings.baseURL + "?capture=1&capture=1",
    settings.baseURL + "?token=private", settings.baseURL + "models/plategauge.onnx?cache=1",
    settings.baseURL + "../outside", settings.baseURL + "#secret",
    settings.baseURL.replace("://", "://user:password@"),
  ]) expect(assetForUrl(target, settings.baseURL, settings.inventory)).toBeUndefined();
  expect(() => reserveDiagnosticsDirectory("relative-output", process.cwd())).toThrow();
  expect(() => reserveDiagnosticsDirectory(process.cwd(), process.cwd())).toThrow();
  const previous = process.env.PLATEGAUGE_CAMERA_SMOKE_MODE;
  try {
    delete process.env.PLATEGAUGE_CAMERA_SMOKE_MODE;
    expect(() => smokeConfiguration()).toThrow("explicitly https or local");
  } finally { process.env.PLATEGAUGE_CAMERA_SMOKE_MODE = previous; }
});

test("retired presentation resource returns 404 without redirects or response-body collection", async () => {
  await expectRetiredResourceUnavailable();
});

test("exact camera landing is inert and preserves source/privacy boundaries", async ({ page, context }) => {
  const { network } = await setupLive(page, context);
  await expect(page.getByTestId("capture-home")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your plate. Before and after.", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Source", exact: true })).toHaveAttribute("href", SOURCE_URL);
  await expect(page.getByRole("link", { name: "Privacy", exact: true })).toHaveAttribute("href", BASE + "legal/CAMERA_PRIVACY_NOTICE.md");
  await expect(page.getByTestId("capture-home")).toContainText(/not validated|unvalidated/i);
  await expect(page.locator('video,input[type="file"]')).toHaveCount(0);
  await expectInert(page, network);
  expect(await page.evaluate(() => isSecureContext && window.top === window.self)).toBe(true);
});

test("capture skip link is painted above navigation and reaches main by keyboard", async ({ page, context }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  const { network } = await setupLive(page, context, "?capture=1");
  const skip = page.getByRole("link", { name: "Skip to capture workflow", exact: true });
  await skip.focus(); await expect(skip).toBeFocused();
  expect(await skip.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return box.left >= 0 && box.right <= innerWidth && box.top >= 0
      && box.bottom <= innerHeight && (element === top || element.contains(top));
  })).toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  await expectInert(page, network);
});

test("modified Privacy click preserves generated capture until current-document exit", async ({ page, context }) => {
  const { network, lifecycle } = await setupLive(page, context, "?capture=1");
  await requireGeneratedCamera(page);
  await takeBefore(page);
  await requireGeneratedCamera(page);
  const originalUrl = page.url();
  const photo = page.getByRole("img", { name: "Your before photo", exact: true });
  const originalPhoto = await photo.getAttribute("src");
  expect(originalPhoto).toMatch(/^blob:/);
  const popupPromise = context.waitForEvent("page");
  await page.getByRole("link", { name: "Privacy", exact: true }).click({ modifiers: ["ControlOrMeta"] });
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded");
  await expect(popup).toHaveURL(smokeConfiguration().baseURL + "legal/CAMERA_PRIVACY_NOTICE.md");
  await expect(page).toHaveURL(originalUrl);
  await expect(photo).toHaveAttribute("src", originalPhoto!);
  await expect(page.getByRole("button", { name: "Continue to after", exact: true })).toBeEnabled();
  await popup.close();
  expect(network.assets.filter((path) => /\/(?:models|ort)\//.test(path))).toEqual([]);
  await expectPrivate(page, network);
  await page.getByRole("link", { name: "Evidence", exact: true }).click();
  await armGeneratedCamera(page);
  await expect.poll(() => [...new Set(lifecycle.revoked)].sort()).toEqual([...new Set(lifecycle.created)].sort());
  await page.getByRole("link", { name: "Capture", exact: true }).click();
  await armGeneratedCamera(page);
  await expect(page.getByRole("img", { name: "Your before photo", exact: true })).toHaveCount(0);
  await expectInert(page, network);
});

test("generated pair invokes the real pinned model only after explicit estimation", async ({ page, context }) => {
  const { network } = await setupLive(page, context, "?capture=1");
  await expectInert(page, network);
  await generatedPair(page);
  const hashes = await cropHashes(page);
  expect(hashes[0]).not.toBe(hashes[1]);
  expect(network.assets.filter((path) => /\/(?:models|ort)\//.test(path))).toEqual([]);
  const mass = page.getByRole("textbox", { name: "Starting food mass (g, optional)", exact: true });
  await mass.fill("250.5");
  await page.getByRole("button", { name: "Estimate remaining", exact: true }).click();
  const result = page.getByTestId("experimental-estimate-result");
  await expect(result).toBeVisible(); await expect(result).toBeFocused();
  await expect(result).toHaveAttribute("data-model-version", MODEL_VERSION);
  const fraction = Number(await result.getAttribute("data-leftover-fraction"));
  expect(Number.isFinite(fraction)).toBe(true); expect(fraction).toBeGreaterThanOrEqual(0); expect(fraction).toBeLessThanOrEqual(1);
  expect(Number(await result.getAttribute("data-remaining-mass-g"))).toBeCloseTo(fraction * 250.5, 10);
  await expect(result).toContainText(/unvalidated/i);
  await expect(result).not.toContainText(/empirical 90%|synthetic test cycle|test-adapter/i);
  await network.settle(); expect(network.modelHashes).toContain(MODEL_SHA256);
  expect(network.verified.has("ort/ort-wasm-simd-threaded.wasm")).toBe(true);
  await page.getByRole("button", { name: "Clear photos", exact: true }).click();
  await expect(result).toHaveCount(0);
  const audit = await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit);
  expect(audit.workerStops).toBeGreaterThanOrEqual(audit.workerStarts);
  expect([...new Set(audit.revokedUrls)].sort()).toEqual([...new Set(audit.createdUrls)].sort());
  await expectPrivate(page, network);
});

test("explicit generated session survives reload without automatic camera or inference", async ({ page, context }) => {
  const { network } = await setupLive(page, context, "?capture=1");
  await generatedPair(page);
  const mass = page.getByRole("textbox", { name: "Starting food mass (g, optional)", exact: true });
  await mass.fill("400"); const before = await cropHashes(page);
  const file = await saveSession(page);
  const record = JSON.parse(file.buffer.toString("utf8")) as Record<string, unknown>;
  expect(Object.keys(record).sort()).toEqual(["after", "before", "checksum", "compatibility", "format", "startingMass", "version"]);
  await page.reload({ waitUntil: "domcontentloaded" }); await armGeneratedCamera(page);
  await resumeSession(page, file);
  await expect(mass).toHaveValue("400");
  expect(await cropHashes(page)).toEqual(before);
  await expectInert(page, network);
  await page.getByRole("button", { name: "Clear photos", exact: true }).click();
  await expect(page.getByRole("img", { name: /Your before photo|Before photo reference/ })).toHaveCount(0);
  await expect(page.getByTestId("session-controls")).toContainText(/unencrypted/i);
  await expect(page.getByTestId("session-controls")).toContainText(/does not delete downloaded/i);
  await expectPrivate(page, network);
});

test("evidence navigation and ambiguous URLs release photos and remain inert", async ({ page, context }) => {
  const { network, lifecycle } = await setupLive(page, context, "?capture=1");
  await generatedPair(page);
  await page.getByRole("link", { name: "Evidence", exact: true }).click();
  await armGeneratedCamera(page);
  await expect(page.getByRole("complementary", { name: "About these results", exact: true })).toContainText("not validation of camera estimates");
  await expect(page.locator(".footer-disclosure")).toHaveCount(0);
  await expect(page.getByText(/Substantially AI-assisted/i)).toHaveCount(0);
  await expect(page.getByText(/accepts no uploads and sends no inference API requests/i)).toHaveCount(0);
  const footer = page.getByRole("contentinfo");
  await expect(footer.getByRole("link", { name: "Privacy", exact: true })).toHaveAttribute("href", BASE + "legal/PRIVACY_NOTICE.md");
  await expect(footer.getByRole("link", { name: "Notices", exact: true })).toHaveAttribute("href", BASE + "legal/NOTICE.txt");
  await expect(page.getByRole("link", { name: "AI-assistance disclosure", exact: true })).toHaveCount(0);
  await expect(page.locator('a[href*="AI_ASSISTANCE"]')).toHaveCount(0);
  await expect(page.getByText(/AI-assisted post-hoc/i)).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    const overlaps = await page.evaluate(() => {
      const failures: string[] = [];
      for (const card of Array.from(document.querySelectorAll(".finding-metric, .metric-card"))) {
        const selectors = card.classList.contains("finding-metric") ? ["span", "strong", "p"] : ["strong", "h3", "p"];
        const children = selectors.map((selector) => card.querySelector(selector));
        if (children.some((child) => !child)) { failures.push("Missing metric text"); continue; }
        for (let index = 1; index < children.length; index++) {
          if (children[index - 1]!.getBoundingClientRect().bottom + 4 > children[index]!.getBoundingClientRect().top) {
            failures.push("Metric value and caption overlap or lack spacing");
          }
        }
      }
      if (document.documentElement.scrollWidth > innerWidth + 1) failures.push("Page exceeds viewport");
      return failures;
    });
    expect(overlaps, `Metric layout at ${width}px`).toEqual([]);
  }
  await expect(page.getByRole("banner")).toHaveCount(1);
  await expect(page.getByTestId("camera-capture")).toHaveCount(0);
  await expect.poll(() => [...new Set(lifecycle.revoked)].sort()).toEqual([...new Set(lifecycle.created)].sort());
  await expectPrivate(page, network);
  for (const query of ["?unknown=1", "?capture=1&view=evidence"]) {
    await page.goto(BASE + query); await armGeneratedCamera(page);
    await expect(page.getByTestId("capture-home")).toBeVisible();
    await expectInert(page, network);
  }
});
