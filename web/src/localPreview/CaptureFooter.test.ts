import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CaptureFooter from "./CaptureFooter";

afterEach(() => { cleanup(); vi.unstubAllEnvs(); });

describe("camera candidate notices", () => {
  it("uses same-origin candidate privacy and attribution paths under the deployment base", () => {
    vi.stubEnv("BASE_URL", "/plategauge/");
    render(createElement(CaptureFooter));
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/plategauge/legal/CAMERA_PRIVACY_NOTICE.md");
    expect(screen.getByRole("link", { name: "Attribution & notices" })).toHaveAttribute("href", "/plategauge/legal/NOTICE.txt");
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Yuita Arum Sari, Yudi Arimba Wani, and Atsushi Nakazawa");
    expect(screen.getByRole("contentinfo")).toHaveTextContent("ordinary request metadata");
  });

  it("links the exact source identity supplied by the build", () => {
    const source = "https://github.com/aldaqrouqtaysir/plategauge/tree/0123456789abcdef0123456789abcdef01234567";
    vi.stubEnv("VITE_SOURCE_URL", source);
    render(createElement(CaptureFooter));
    expect(screen.getByRole("link", { name: "Source" })).toHaveAttribute("href", source);
    expect(screen.getByRole("link", { name: "Source" })).toHaveAttribute("rel", "noreferrer");
  });

  it("notifies the owner before each notice navigation without other actions", () => {
    const onNavigate = vi.fn();
    render(createElement(CaptureFooter, { onNavigate }));
    expect(onNavigate).not.toHaveBeenCalled();
    for (const name of ["Privacy", "Attribution & notices", "Source"]) {
      const link = screen.getByRole("link", { name });
      // Suppress jsdom navigation after the React handler has observed primary intent.
      document.addEventListener("click", (event) => event.preventDefault(), { once: true });
      fireEvent.click(link);
    }
    expect(onNavigate).toHaveBeenCalledTimes(3);
  });

  it("keeps ownership when a notice opens elsewhere or activation is prevented", () => {
    const onNavigate = vi.fn(); render(createElement(CaptureFooter, { onNavigate }));
    const link = screen.getByRole("link", { name: "Privacy" });
    for (const options of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }]) {
      document.addEventListener("click", (event) => event.preventDefault(), { once: true });
      fireEvent.click(link, options);
    }
    link.addEventListener("click", (event) => event.preventDefault(), { once: true }); fireEvent.click(link);
    expect(onNavigate).not.toHaveBeenCalled();
  });
});
