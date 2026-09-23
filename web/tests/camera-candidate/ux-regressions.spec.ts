import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { expectInert, expectPrivate, saveSession, setup, takeBefore, takePair } from "./support";

for (const width of [320, 768, 980, 1440]) {
  test(`concise capture guidance stays readable and keyboard-accessible at ${width}px`, async ({ page, context, baseURL }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const { network } = await setup(page, context, baseURL);
    await expect(page.locator(".cp-intro > p")).toHaveCount(0);
    await expect(page.getByText(/Take two photos\. Match the framing/)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Open camera", exact: true })).toHaveAccessibleDescription(/Not validated for your photos or field use; not a scale measurement/);
    await expect(page.locator("#rc-session-disclosure")).toBeVisible();
    await expect(page.locator("#rc-session-disclosure")).toContainText("unencrypted");
    const privacy = page.locator("details.rc-privacy-details");
    const summary = privacy.locator("summary");
    await expect(privacy).not.toHaveAttribute("open");
    await expect(privacy.locator("p").first()).not.toBeVisible();
    const heading = await page.locator(".cp-intro h1").boundingBox();
    const boundary = await page.locator("#rc-capture-disclosure").boundingBox();
    expect(heading).not.toBeNull(); expect(boundary).not.toBeNull();
    expect(heading!.y + heading!.height + 12).toBeLessThanOrEqual(boundary!.y);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`concise-capture-${width}.png`), fullPage: true });
    await summary.focus(); await expect(summary).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(privacy).toHaveAttribute("open");
    await expect(privacy.locator("p").first()).toBeVisible();
    await expect(privacy).toContainText("Session files are downloaded only when you choose Save session");
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.keyboard.press("Enter");
    await expect(privacy).not.toHaveAttribute("open");
    await expectInert(page, network);
  });
}

test("capture skip link is visibly painted above navigation and reaches main by keyboard", async ({ page, context, baseURL }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  const { network } = await setup(page, context, baseURL);
  const skip = page.getByRole("link", { name: "Skip to capture workflow" });
  await skip.focus(); await expect(skip).toBeFocused();
  expect(await skip.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return box.left >= 0 && box.right <= innerWidth && box.top >= 0
      && (element === top || element.contains(top));
  })).toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  await expectInert(page, network);
});

test("opening a privacy notice in a new tab preserves unsaved photos until actual exit", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  await takeBefore(page);
  const originalUrl = page.url();
  const originalPhoto = await page.getByRole("img", { name: "Your before photo", exact: true }).getAttribute("src");
  const popupPromise = context.waitForEvent("page");
  await page.getByRole("link", { name: "Privacy", exact: true }).click({ modifiers: ["ControlOrMeta"] });
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded");
  await expect(popup).toHaveURL(/\/legal\/CAMERA_PRIVACY_NOTICE\.md$/);
  await expect(page).toHaveURL(originalUrl);
  await expect(page.getByRole("img", { name: "Your before photo", exact: true })).toHaveAttribute("src", originalPhoto!);
  await expect(page.getByRole("button", { name: "Continue to after", exact: true })).toBeEnabled();
  await popup.close();
  await expectPrivate(page, network);
  // In-document navigation still discards capture state; no persistence is introduced.
  await page.getByRole("link", { name: "Evidence", exact: true }).click();
  await page.getByRole("link", { name: "Capture", exact: true }).click();
  await expect(page.getByRole("img", { name: "Your before photo", exact: true })).toHaveCount(0);
  await expectInert(page, network);
});

test("starting mass length agrees with session export before a download is offered", async ({ page, context, baseURL }) => {
  const { network } = await setup(page, context, baseURL);
  await takePair(page);
  const mass = page.getByLabel("Starting food mass (g, optional)");
  await expect(mass).toHaveAttribute("maxlength", "64");
  await mass.fill("0".repeat(64) + "1");
  expect((await mass.inputValue()).length).toBeLessThanOrEqual(64);
  await expect(mass).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByRole("button", { name: "Save session", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Estimate remaining", exact: true })).toBeDisabled();
  const valid = "0".repeat(63) + "1";
  await mass.fill(valid); await expect(mass).toHaveAttribute("aria-invalid", "false");
  const session = await saveSession(page);
  expect((JSON.parse(session.buffer.toString("utf8")) as { startingMass: string }).startingMass).toBe(valid);
  await expect(page.getByTestId("session-error")).toHaveCount(0);
  await expectPrivate(page, network);
});
