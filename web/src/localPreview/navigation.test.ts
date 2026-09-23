import type { MouseEvent as ReactMouseEvent } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { isCurrentDocumentNavigation } from "./navigation";

function activation(options: MouseEventInit = {}, attributes: Record<string, string> = {}) {
  const anchor = document.createElement("a"); anchor.href = "/?view=evidence";
  for (const [name, value] of Object.entries(attributes)) anchor.setAttribute(name, value);
  const event = new MouseEvent("click", { button: 0, cancelable: true, ...options });
  Object.defineProperty(event, "currentTarget", { value: anchor });
  return event as unknown as ReactMouseEvent<HTMLAnchorElement>;
}

afterEach(() => document.querySelector("base[data-navigation-test]")?.remove());

describe("current-document navigation intent", () => {
  const localTargets: Record<string, string>[] = [{}, { target: "" }, { target: "_self" }, { target: "_SELF" }];
  it.each(localTargets)("clears for unmodified primary activation %j", (attributes) => {
    expect(isCurrentDocumentNavigation(activation({}, attributes))).toBe(true);
  });
  it.each([{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }, { button: 1 }, { button: 2 }])("keeps the source session for %j", (options) => {
    expect(isCurrentDocumentNavigation(activation(options))).toBe(false);
  });
  it.each(["_blank", "reader", "_parent", "_top"])("keeps the source session for target %s", (target) => {
    expect(isCurrentDocumentNavigation(activation({}, { target }))).toBe(false);
  });
  it("respects prevented events and downloads", () => {
    const event = activation(); event.preventDefault();
    expect(isCurrentDocumentNavigation(event)).toBe(false);
    expect(isCurrentDocumentNavigation(activation({}, { download: "" }))).toBe(false);
  });
  it("respects a document target unless the anchor explicitly selects itself", () => {
    const base = document.createElement("base"); base.target = "_blank"; base.dataset.navigationTest = "1"; document.head.append(base);
    expect(isCurrentDocumentNavigation(activation())).toBe(false);
    expect(isCurrentDocumentNavigation(activation({}, { target: "_self" }))).toBe(true);
  });
});
