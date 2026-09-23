import type { MouseEvent } from "react";

/** Clear a capture only when this activation intends to leave its document. */
export function isCurrentDocumentNavigation(event: MouseEvent<HTMLAnchorElement>): boolean {
  if (event.defaultPrevented || event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return false;
  const anchor = event.currentTarget;
  if (anchor.hasAttribute("download")) return false;
  const target = anchor.getAttribute("target")
    ?? anchor.ownerDocument.querySelector("base[target]")?.getAttribute("target") ?? "";
  return target === "" || target.toLowerCase() === "_self";
}
