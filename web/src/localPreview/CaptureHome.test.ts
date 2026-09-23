import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CaptureHome from "./CaptureHome";

afterEach(cleanup);

describe("experimental camera capability presentation", () => {
  it("describes the existing baseline without promising improved or validated estimates", () => {
    const view = render(createElement(CaptureHome));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Your plate. Before and after.");
    expect(view.container).toHaveTextContent("Experimental estimate using the v1 paired research baseline. Not validated for your photos and not a scale measurement.");
    expect(screen.getByRole("link", { name: "Start a capture" })).toHaveAccessibleDescription(/Not validated for your photos and not a scale measurement/);
    expect(view.container).toHaveTextContent("Your camera stays off until you choose Open camera.");
    expect(view.container).toHaveTextContent("it does not learn from your photos");
    expect(view.container).not.toHaveTextContent("Capture and review only. No food estimate is generated.");
    expect(view.container.querySelector("video, canvas, input")).toBeNull();
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("LeFood-Set v1");
    expect(view.container).not.toHaveTextContent("local-development only");
  });

  it("keeps explicit capture and evidence destinations, illustration labeling, and scope context", () => {
    render(createElement(CaptureHome));
    expect(screen.getByRole("link", { name: "Start a capture" })).toHaveAttribute("href", "/?capture=1");
    expect(screen.getByRole("link", { name: "Explore the evidence" })).toHaveAttribute("href", "/?view=evidence");
    expect(screen.getByText("Illustrative pair · not photographs or model output.")).toBeInTheDocument();
    const about = document.getElementById("about");
    expect(about).toHaveTextContent("no confidence interval or operational-use claim is made");
    expect(about).toHaveTextContent("Optional grams are calculated only from a starting mass you provide");
    expect(about).toHaveTextContent("Photos are not uploaded or automatically saved");
    expect(about).toHaveTextContent("unencrypted file containing the photos and optional starting mass");
    expect(about).toHaveTextContent("does not delete downloaded files");
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/legal/CAMERA_PRIVACY_NOTICE.md");
    expect(screen.getByRole("link", { name: "Attribution & notices" })).toHaveAttribute("href", "/legal/NOTICE.txt");
  });
});
