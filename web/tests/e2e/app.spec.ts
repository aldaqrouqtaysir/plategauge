import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("presents the frozen negative finding instead of a custom-image estimator", async ({ page }) => {
  await expect(page.getByRole("heading", { name: /including where it failed/i })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "The paired model did not outperform after-only." }),
  ).toBeVisible();
  const primaryFinding = page.getByRole("complementary", { name: "Primary finding" });
  await expect(primaryFinding.getByText("12.28 pp")).toBeVisible();
  await expect(primaryFinding.getByText("9.79 pp")).toBeVisible();
  await expect(page.getByText(/Paired was \+2.49 percentage points worse/)).toBeVisible();
  await expect(page.getByText(/0 means none of the recorded mass remained/)).toBeVisible();
  await expect(page.getByText(/benchmark and failure explorer, not an unrestricted estimator/i)).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await expect(page.locator("#example-selection-context")).toContainText("uploads and new-image estimates are unavailable here");
  await expect(page.getByRole("heading", { name: "Target-range errors" })).toBeVisible();
  const worstSlice = page.locator(".slice-row").filter({ hasText: "(0.50, 0.75]" });
  await expect(worstSlice).toContainText("n=57");
  await expect(worstSlice).toContainText("27.45 pp");
  const engineering = page.locator("#engineering");
  await expect(
    engineering.getByRole("heading", { name: /compact, browser-checked candidate/i }),
  ).toBeVisible();
  await expect(engineering).toContainText("10.36 MB");
  await expect(engineering).toContainText("22.12 ms");
  await expect(engineering).toContainText("45.64 MiB");
  await expect(engineering).toContainText(/do not support phone, unmeasured-browser, production/i);
});

test("exposes the complete comparison, category, robustness, and downloadable evidence", async ({
  page,
}) => {
  const comparisons = page.getByRole("article", { name: /Every frozen workload/i });
  await expect(comparisons).toContainText("Observer score");
  await expect(comparisons).toContainText("After-only MobileNet");
  await expect(comparisons).toContainText("Paired MobileNet");
  await expect(comparisons).toContainText("Wrong-pair control");
  await expect(comparisons).toContainText(/destructive input\/target mismatch/i);

  const categories = page.getByRole("article", { name: /aggregate result was not uniform/i });
  await expect(categories).toContainText("categories favored after-only");
  await categories.getByText("Inspect all 34 categories and support counts").click();
  await expect(categories.locator("tbody tr")).toHaveCount(34);
  await expect(categories).toContainText(/categories 034–049 had no archived images/i);

  const robustness = page.getByRole("article", { name: /routine blur breached/i });
  await expect(robustness).toContainText("15.02 pp");
  await expect(robustness).toContainText(/3.00-point gate breached/i);
  await expect(robustness).toContainText("Same image supplied twice");
  await expect(robustness).toContainText(/blocks a robustness claim/i);

  await expect(page.getByText(/254 of 514 targets \(49.4%\)/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Download evidence JSON/i })).toHaveAttribute(
    "href",
    /evidence\/benchmark-evidence\.json$/,
  );
});

test("explores disclosed successes and largest errors with source-grounded values", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Ikan Acar Kuning" })).toBeVisible();
  await expect(page.getByText("18 g after")).toBeVisible();
  await expect(page.getByText("39 g before")).toBeVisible();
  await expect(page.locator(".mass-equation").getByText("46.2%", { exact: true })).toBeVisible();

  await page.getByTestId("example-lefood-0530").click();
  await expect(page.getByRole("heading", { name: "Oseng Tahu" })).toBeVisible();
  await expect(page.getByText("Largest error · rank 1")).toBeVisible();
  await expect(page.getByText(/possible image-to-mass/i)).toBeVisible();
  const images = page.getByTestId("fixed-image-pair").locator("img");
  await expect(images).toHaveCount(2);
  await expect(images.first()).toHaveAttribute("src", /lefood-0530-before\.jpg$/);
  await expect(images.last()).toHaveAttribute("src", /lefood-0530-after\.jpg$/);
});

test("runs only a fixed bundled replay without post-readiness network traffic", async ({ page }) => {
  await page.goto("/?benchmark=1");
  await expect(page.getByTestId("model-ready")).toContainText("Test adapter active");
  const fixedReady = page.getByTestId("fixed-example-ready");
  await expect(fixedReady).toContainText("lefood-0192 ready");
  await expect(fixedReady).toHaveAttribute("data-sample-id", "lefood-0192");
  await expect(fixedReady).toHaveAttribute(
    "data-before-sha256",
    "e90d69a5f213cfa5b30c651a5e9572308adb245bed9bc87c02a8d5c316c44506",
  );
  await expect(fixedReady).toHaveAttribute(
    "data-after-sha256",
    "ea71f3b1113d564bf04d1056c6177bdc063194f5a84fb88b9150158997a28b90",
  );
  const requests: string[] = [];
  page.on("request", (request) => {
    const protocol = new URL(request.url()).protocol;
    if (protocol === "http:" || protocol === "https:") {
      requests.push(`${request.method()} ${request.url()}`);
    }
  });

  const replayButton = page.getByTestId("run-fixed-example");
  await expect(replayButton).toBeEnabled();
  await replayButton.click();

  const output = page.getByTestId("runtime-output");
  await expect(output).toContainText("Synthetic test cycle");
  await expect(output).toContainText("No numeric model output is rendered");
  await expect(output).not.toContainText(/%/);
  await expect(output).toHaveAttribute("data-processing-ms", /\d+\.\d{6}/);
  await expect(output).toHaveAttribute("data-sample-id", "lefood-0192");
  await expect(page.getByText(/Empirical 90% interval/i)).toHaveCount(0);
  expect(requests).toEqual([]);
});

test("keeps the benchmark harness unlinked and absent from the normal public route", async ({ page }) => {
  await expect(page.getByTestId("benchmark-harness")).toHaveCount(0);
  await expect(page.locator('a[href*="benchmark=1"]')).toHaveCount(0);
  await expect(page.getByTestId("model-ready")).toHaveCount(0);
});

test("uses a keyboard-complete single-selection example group", async ({ page }) => {
  await page.locator(".skip-link").focus();
  await expect(page.locator(".skip-link")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();

  const chooser = page.getByRole("radiogroup", {
    name: "Choose one frozen benchmark example",
  });
  await expect(chooser.getByRole("radio")).toHaveCount(10);
  const current = page.getByTestId("example-lefood-0192");
  await expect(current).toHaveAttribute("aria-checked", "true");
  await expect(current).toHaveAttribute("aria-controls", "selected-example-panel");

  const failureButton = page.getByTestId("example-lefood-0320");
  await failureButton.focus();
  await page.keyboard.press("Enter");
  await expect(failureButton).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("heading", { name: "Telur Mata Sapi" })).toBeVisible();

  await page.keyboard.press("ArrowDown");
  const nextFailure = page.getByTestId("example-lefood-0226");
  await expect(nextFailure).toBeFocused();
  await expect(nextFailure).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("heading", { name: "Bali Telur" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText(
    "Selected Bali Telur, largest error, paired absolute error 84.0 pp",
  );
});

test("keeps navigation and readable compact content at a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  const mobileNav = page.getByRole("navigation", { name: "Primary navigation" });
  await expect(mobileNav.getByRole("link", { name: "Results", exact: true })).toBeVisible();
  await expect(mobileNav.getByRole("link", { name: "Evidence explorer", exact: true })).toBeVisible();
  await expect(mobileNav.getByRole("link", { name: "Engineering", exact: true })).toBeVisible();
  await expect(mobileNav.getByRole("link", { name: "Limits", exact: true })).toBeVisible();
  await expect(page.locator(".release-label-wide")).toBeHidden();
  await expect(page.locator(".release-label-compact")).toHaveText("v1.0.2 · benchmark explorer");

  await expect(page.getByRole("heading", { name: /including where it failed/i })).toBeVisible();
  await mobileNav.getByRole("link", { name: "Evidence explorer", exact: true }).click();
  const explorerHeading = page.getByRole("heading", {
    name: /close predictions and the hard failures/i,
  });
  const positions = await page.evaluate(() => ({
    headerBottom: document.querySelector(".site-header")!.getBoundingClientRect().bottom,
    headingTop: document.querySelector("#explorer-title")!.getBoundingClientRect().top,
  }));
  expect(positions.headingTop).toBeGreaterThanOrEqual(positions.headerBottom);
  await expect(explorerHeading).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  const tooSmall = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => {
        const hasOwnText = Array.from(element.childNodes).some(
          (node) => node.nodeType === Node.TEXT_NODE && Boolean(node.textContent?.trim()),
        );
        const style = window.getComputedStyle(element);
        return hasOwnText && style.display !== "none" && style.visibility !== "hidden";
      })
      .map((element) => ({
        text: element.textContent?.trim().slice(0, 60),
        px: Number.parseFloat(window.getComputedStyle(element).fontSize),
      }))
      .filter(({ px }) => px < 11.99),
  );
  expect(tooSmall).toEqual([]);
  await expect(page.locator(".metric-card").first()).toHaveCSS("min-height", "0px");
});

test("has no automatically detectable serious accessibility violations", async ({ page }) => {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(results.violations).toEqual([]);
});
