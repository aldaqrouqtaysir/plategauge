/** Local workflow observations only. This is not an accuracy or device certification. */
export const DEVICE_CHECKS = {
  permissionRecovery: "Camera permission denial and retry",
  framingReview: "Live guide and model-input review",
  explicitEstimate: "Estimate starts only when requested",
  cancelRetake: "Cancel and retake stop stale work",
  sessionResume: "Save, reload and resume your own session",
  hiddenReturn: "Hide or lock, then return to the page",
  clearCleanup: "Clear removes photos from this page",
} as const;

export type CheckOutcome = "untested" | "pass" | "fail" | "not_applicable";
export type CheckResults = Record<keyof typeof DEVICE_CHECKS, CheckOutcome>;
export type DeviceKind = "unspecified" | "laptop_desktop" | "android" | "iphone_ipad" | "other";
export type BrowserKind = "unspecified" | "chrome" | "edge" | "firefox" | "safari" | "other";
export type TestEnvironment = "unspecified" | "physical_device" | "simulated_camera";

export interface DeviceCheckSetup {
  device: DeviceKind;
  browser: BrowserKind;
  browserVersion: string;
  environment: TestEnvironment;
}

export interface DeviceObservations {
  cameraReadyNow: boolean;
  beforePresent: boolean;
  afterPresent: boolean;
  latestCaptureMs: number | null;
  latestEstimateWallMs: number | null;
  latestModelProcessingMs: number | null;
}

export function emptyCheckResults(): CheckResults {
  return Object.fromEntries(Object.keys(DEVICE_CHECKS).map((key) => [key, "untested"])) as CheckResults;
}

function choice<T extends string>(value: unknown, allowed: readonly T[]): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) throw new Error("Choose one of the listed device-check options.");
  return value as T;
}

export function safeDuration(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 3_600_000
    ? Math.round(value * 10) / 10 : null;
}

export function buildDeviceCheckReport(setup: DeviceCheckSetup, checks: CheckResults, observations: DeviceObservations) {
  const version = setup.browserVersion.trim();
  if (version && !/^\d{1,8}(?:\.\d{1,8}){0,3}$/.test(version)) {
    throw new Error("Use a numeric browser version such as 140.0, or leave it blank.");
  }
  const results = Object.fromEntries(Object.keys(DEVICE_CHECKS).map((key) => [
    key, choice(checks[key as keyof CheckResults], ["untested", "pass", "fail", "not_applicable"] as const),
  ])) as CheckResults;
  const reported = Object.values(results);
  return {
    schemaVersion: "plategauge-device-check-v1",
    purpose: "self_reported_local_workflow_check",
    releaseApproval: false,
    accuracyValidation: false,
    setup: {
      device: choice(setup.device, ["unspecified", "laptop_desktop", "android", "iphone_ipad", "other"] as const),
      browser: choice(setup.browser, ["unspecified", "chrome", "edge", "firefox", "safari", "other"] as const),
      browserVersion: version || null,
      environment: choice(setup.environment, ["unspecified", "physical_device", "simulated_camera"] as const),
    },
    checks: results,
    reviewStatus: reported.includes("fail") ? "attention_needed" : reported.includes("untested") || reported.includes("not_applicable")
      || setup.environment === "unspecified" || setup.device === "unspecified" || setup.browser === "unspecified" || !version
      ? "incomplete" : "observations_recorded_not_certified",
    currentPage: {
      cameraReady: observations.cameraReadyNow === true,
      beforePresent: observations.beforePresent === true,
      afterPresent: observations.afterPresent === true,
    },
    latestTimingMs: {
      capturePreparation: safeDuration(observations.latestCaptureMs),
      estimateClickToResult: safeDuration(observations.latestEstimateWallMs),
      modelProcessing: safeDuration(observations.latestModelProcessingMs),
    },
    timingScope: "Latest successful operations only; not p50/p95, cold-load, permission-wait or full-meal duration. Concurrent work can affect timings.",
    peakMemoryMeasured: false,
    limitations: [
      "Operator-selected device, browser and outcomes are not independently verified.",
      "A simulated camera or one physical device cannot validate other devices or food accuracy.",
      "No images, entered food mass, predicted fractions, device IDs, user agent, URLs or names are included.",
      "Clearing the page does not delete downloaded session or check files.",
    ],
  };
}
