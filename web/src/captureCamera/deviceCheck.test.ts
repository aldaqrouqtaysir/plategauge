import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DeviceCheck from "./DeviceCheck";
import { buildDeviceCheckReport, DEVICE_CHECKS, emptyCheckResults, safeDuration, type DeviceCheckSetup, type DeviceObservations } from "./deviceCheckReport";

const setup: DeviceCheckSetup = { device: "laptop_desktop", browser: "firefox", browserVersion: "140.0", environment: "physical_device" };
const observations: DeviceObservations = { cameraReadyNow: false, beforePresent: true, afterPresent: true, latestCaptureMs: 25.52, latestEstimateWallMs: 987.51, latestModelProcessingMs: 780.13 };

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("non-image device-check record", () => {
  it("starts with seven untested checks and never infers physical-device success", () => {
    expect(Object.keys(emptyCheckResults())).toEqual(Object.keys(DEVICE_CHECKS));
    expect(new Set(Object.values(emptyCheckResults()))).toEqual(new Set(["untested"]));
    const record = buildDeviceCheckReport(setup, emptyCheckResults(), observations);
    expect(record.reviewStatus).toBe("incomplete");
    expect(record.releaseApproval).toBe(false);
    expect(record.accuracyValidation).toBe(false);
    expect(record.peakMemoryMeasured).toBe(false);
    expect(record.latestTimingMs).toEqual({ capturePreparation: 25.5, estimateClickToResult: 987.5, modelProcessing: 780.1 });
  });

  it("records complete self-reported checks without certifying them", () => {
    const checks = emptyCheckResults();
    for (const key of Object.keys(checks) as (keyof typeof checks)[]) checks[key] = "pass";
    expect(buildDeviceCheckReport(setup, checks, observations).reviewStatus).toBe("observations_recorded_not_certified");
    checks.hiddenReturn = "fail";
    expect(buildDeviceCheckReport(setup, checks, observations).reviewStatus).toBe("attention_needed");
    checks.hiddenReturn = "not_applicable";
    expect(buildDeviceCheckReport(setup, checks, observations).reviewStatus).toBe("incomplete");
  });

  it.each(["", "140", "140.0", "140.0.1.99999999"])("accepts numeric or omitted version %s", (version) => {
    expect(buildDeviceCheckReport({ ...setup, browserVersion: version }, emptyCheckResults(), observations).setup.browserVersion).toBe(version || null);
  });
  it.each(["<img src=x>", "Firefox 140", "140.1.2.3.4", "1e3", "-1", "999999999", "140\n.0"])("rejects non-version free text %s", (version) => {
    expect(() => buildDeviceCheckReport({ ...setup, browserVersion: version }, emptyCheckResults(), observations)).toThrow("numeric browser version");
  });
  it.each([NaN, Infinity, -1, 3_600_001, "12", null, undefined])("does not fabricate a duration from %s", (value) => {
    expect(safeDuration(value)).toBeNull();
  });
  it("keeps zero time distinct from unknown and validates choices", () => {
    expect(safeDuration(0)).toBe(0);
    expect(safeDuration(3_600_000)).toBe(3_600_000);
    expect(() => buildDeviceCheckReport({ ...setup, device: "SECRET_DEVICE" } as unknown as DeviceCheckSetup, emptyCheckResults(), observations)).toThrow("listed");
    expect(() => buildDeviceCheckReport(setup, { ...emptyCheckResults(), permissionRecovery: "auto_pass" } as never, observations)).toThrow("listed");
  });
  it("allowlists output fields and omits extraneous personal or food data", () => {
    const extendedSetup = { ...setup, owner: "SECRET_NAME", userAgent: "SECRET_UA" };
    const extendedChecks = { ...emptyCheckResults(), unknown: "SECRET_EXTRA" };
    const extendedObservations = { ...observations, photos: "SECRET_PHOTO", initialMassG: 98765, leftoverFraction: 0.12345, url: "SECRET_URL" };
    const record = buildDeviceCheckReport(extendedSetup, extendedChecks, extendedObservations);
    const json = JSON.stringify(record);
    expect(json).not.toMatch(/SECRET|98765|0\.12345/);
    expect(Object.keys(record.currentPage)).toEqual(["cameraReady", "beforePresent", "afterPresent"]);
  });
  it("keeps omitted setup incomplete even if checks are marked worked", () => {
    const checks = emptyCheckResults();
    for (const key of Object.keys(checks) as (keyof typeof checks)[]) checks[key] = "pass";
    for (const missing of [{ device: "unspecified" }, { browser: "unspecified" }, { browserVersion: "" }, { environment: "unspecified" }] as Partial<DeviceCheckSetup>[]) {
      expect(buildDeviceCheckReport({ ...setup, ...missing }, checks, observations).reviewStatus).toBe("incomplete");
    }
  });
});

describe("explicit optional device-check UI", () => {
  function downloads() {
    const create = vi.fn<(blob: Blob) => string>(() => "blob:synthetic-device-report");
    const revoke = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    return { create, revoke, click };
  }
  it("is collapsed and inert until an explicit action", () => {
    const { create, click } = downloads();
    const view = render(createElement(DeviceCheck, { observations }));
    expect(view.container.querySelector("details")).not.toHaveAttribute("open");
    expect(create).not.toHaveBeenCalled(); expect(click).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Camera used for this check")).toHaveValue("unspecified");
    expect(screen.getByLabelText("Camera permission denial and retry")).toHaveValue("untested");
    expect(view.container).toHaveTextContent("Selecting a device here does not establish compatibility or accuracy.");
    expect(view.container).not.toHaveTextContent("local-development only");
  });
  it("downloads only a JSON check on click, then revokes its temporary URL", async () => {
    vi.useFakeTimers();
    const { create, click, revoke } = downloads();
    render(createElement(DeviceCheck, { observations }));
    fireEvent.change(screen.getByLabelText("Device type"), { target: { value: "laptop_desktop" } });
    fireEvent.change(screen.getByLabelText("Browser", { exact: true }), { target: { value: "firefox" } });
    fireEvent.change(screen.getByLabelText(/Browser version/), { target: { value: "140.0" } });
    fireEvent.change(screen.getByLabelText("Camera used for this check"), { target: { value: "simulated_camera" } });
    fireEvent.change(screen.getByLabelText("Camera permission denial and retry"), { target: { value: "fail" } });
    fireEvent.click(screen.getByRole("button", { name: "Download device check" }));
    expect(create).toHaveBeenCalledOnce(); expect(click).toHaveBeenCalledOnce();
    const blob = create.mock.calls[0]![0];
    expect(blob.type).toBe("application/json"); expect(blob.size).toBeLessThan(5_000);
    expect(document.querySelector('a[download="plategauge-device-check.json"]')).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("not photos or estimates");
    expect(revoke).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(revoke).toHaveBeenCalledExactlyOnceWith("blob:synthetic-device-report");
  });
  it("cleans up pending download URLs on unmount", () => {
    vi.useFakeTimers();
    const { revoke } = downloads();
    const view = render(createElement(DeviceCheck, { observations }));
    fireEvent.click(screen.getByRole("button", { name: "Download device check" }));
    view.unmount();
    expect(revoke).toHaveBeenCalledOnce(); expect(vi.getTimerCount()).toBe(0);
  });
  it("shows invalid version feedback without creating a file", () => {
    const { create } = downloads();
    render(createElement(DeviceCheck, { observations }));
    fireEvent.change(screen.getByLabelText(/Browser version/), { target: { value: "my-device-name" } });
    fireEvent.click(screen.getByRole("button", { name: "Download device check" }));
    expect(screen.getByRole("alert")).toHaveTextContent("numeric browser version"); expect(create).not.toHaveBeenCalled();
  });
  it("sanitizes failures, revokes the URL and removes the anchor", () => {
    const { click, revoke } = downloads();
    click.mockImplementation(() => { throw new Error("SECRET_DEVICE_DETAIL"); });
    render(createElement(DeviceCheck, { observations }));
    fireEvent.click(screen.getByRole("button", { name: "Download device check" }));
    expect(screen.getByRole("alert")).toHaveTextContent("could not be prepared");
    expect(screen.getByRole("alert")).not.toHaveTextContent("SECRET");
    expect(revoke).toHaveBeenCalledOnce(); expect(document.querySelector("a[download]")).toBeNull();
  });
  it("resets operator fields without deleting downloads or reporting a pass", () => {
    downloads();
    render(createElement(DeviceCheck, { observations: { ...observations, latestCaptureMs: null, latestEstimateWallMs: NaN } }));
    fireEvent.change(screen.getByLabelText("Device type"), { target: { value: "android" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset device check" }));
    expect(screen.getByLabelText("Device type")).toHaveValue("unspecified");
    expect(screen.getByRole("status")).toHaveTextContent("Downloaded files are not deleted");
    expect(screen.getAllByText("Not observed")).toHaveLength(2);
  });
});
