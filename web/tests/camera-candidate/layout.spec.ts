import { expect, test } from "@playwright/test";
import { BASE, expectInert, setup } from "./support";

for (const width of [320, 768, 980, 1440]) {
  test(`evidence metric groups and contextual captions remain separated at ${width}px`, async ({ page, context, baseURL }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const { network } = await setup(page, context, baseURL, "?view=evidence");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Explore the result.Including where it failed.");
    await expect(page.getByRole("heading", { level: 1 })).not.toContainText("—");
    await expect(page.locator(".finding-metric")).toHaveCount(2);
    await expect(page.locator(".finding-metric").nth(0).locator("strong")).toHaveText("12.28 pp");
    await expect(page.locator(".finding-metric").nth(1).locator("strong")).toHaveText("9.79 pp");
    await expect(page.locator(".study-facts dd")).toHaveText(["514", "34", "5"]);
    await expect(page.locator(".section-heading > p")).toHaveCount(0);
    await expect(page.locator("#example-selection-context")).toContainText("not a random sample");
    await expect(page.locator(".example-chooser")).toHaveAttribute("aria-describedby", "example-selection-context");
    await expect(page.locator(".method-grid")).toContainText("Food category never entered the model.");
    await expect(page.locator(".method-grid")).toContainText("Every pair appeared in one untouched outer fold");
    await expect(page.locator(".review-note")).toContainText("Post-hoc visual review hypothesis.");
    await expect(page.getByText(/AI-assistance disclosure|AI-assisted post-hoc|Substantially AI-assisted/i)).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Privacy", exact: true })).toHaveAttribute("href", `${BASE}legal/PRIVACY_NOTICE.md`);
    await expect(page.getByRole("link", { name: "Notices", exact: true })).toHaveAttribute("href", `${BASE}legal/NOTICE.txt`);

    const failures = await page.evaluate(() => {
      const issues: string[] = [];
      const rect = (element: Element) => element.getBoundingClientRect();
      const separated = (first: DOMRect, second: DOMRect) => first.right <= second.left + 0.5
        || second.right <= first.left + 0.5 || first.bottom <= second.top + 0.5 || second.bottom <= first.top + 0.5;
      const ordered = (parent: Element, selectors: string[], label: string) => {
        const children = selectors.map((selector) => parent.querySelector(selector));
        if (children.some((child) => !child)) { issues.push(`${label}: missing text block`); return; }
        const parentRect = rect(parent);
        for (let index = 0; index < children.length; index++) {
          const child = children[index]!;
          const bounds = rect(child);
          if (bounds.width <= 0 || bounds.height <= 0) issues.push(`${label}: empty text bounds`);
          if (bounds.left < parentRect.left - 0.5 || bounds.right > parentRect.right + 0.5) issues.push(`${label}: horizontal clipping`);
          if (child.scrollWidth > child.clientWidth + 1) issues.push(`${label}: overflowing text`);
          if (index > 0 && rect(children[index - 1]!).bottom + 4 > bounds.top) issues.push(`${label}: adjacent text lacks clear spacing`);
          const style = getComputedStyle(child);
          if (parseFloat(style.lineHeight) < parseFloat(style.fontSize)) issues.push(`${label}: compressed line height`);
        }
      };
      const metrics = [...document.querySelectorAll(".finding-metric")];
      metrics.forEach((metric, index) => ordered(metric, ["span", "strong", "p"], `primary metric ${index}`));
      if (metrics.length === 2 && !separated(rect(metrics[0]!), rect(metrics[1]!))) issues.push("Primary metric groups overlap");
      const finding = document.querySelector(".negative-finding");
      if (!finding || metrics.some((metric) => rect(metric).bottom + 8 > rect(finding).top)) issues.push("Finding callout overlaps metric groups");
      document.querySelectorAll(".metric-card").forEach((card, index) => ordered(card, ["strong", "h3", "p"], `result metric ${index}`));
      document.querySelectorAll(".method-grid li").forEach((card, index) => ordered(card, ["span", "h3", "p"], `method card ${index}`));
      for (const item of document.querySelectorAll(".study-facts > div")) {
        const label = item.querySelector("dt"), value = item.querySelector("dd");
        if (!label || !value || !separated(rect(label), rect(value))) issues.push("Study fact value overlaps its label");
      }
      const caption = document.querySelector("#example-selection-context");
      const choices = [...document.querySelectorAll(".chooser-group")];
      if (!caption || choices.some((choice) => rect(caption).bottom > rect(choice).top + 0.5)) issues.push("Selection caption overlaps choices");
      if (document.documentElement.scrollWidth > innerWidth + 1) issues.push("Page overflows viewport");
      return issues;
    });
    expect(failures).toEqual([]);
    await expectInert(page, network);
  });
}
