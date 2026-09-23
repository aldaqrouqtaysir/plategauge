import { describe, expect, it } from "vitest";
import { EstimateError, estimateErrorMessage, type EstimateErrorCode } from "./errors";

describe("allowlisted estimate recovery messages", () => {
  it.each([
    ["unavailable_context", "secure"], ["cancelled", "cancelled"],
    ["mismatched_shape", "orientation"], ["invalid_input", "Retake"],
    ["identical_pair", "distinct"], ["timeout", "too long"],
    ["invalid_result", "valid estimate"], ["worker_failed", "stopped"],
    ["unreadable_result", "read"], ["transfer_failed", "prepare"], ["unknown", "Retry"],
  ] satisfies [EstimateErrorCode, string][])("offers actionable guidance for %s", (code, expected) => {
    const error = new EstimateError(code);
    expect(error.name).toBe("EstimateError");
    expect(estimateErrorMessage(error)).toContain(expected);
    error.message = "private photo data must not reach the page";
    expect(estimateErrorMessage(error)).toContain(expected);
    expect(estimateErrorMessage(error)).not.toContain("private photo");
  });

  it.each([undefined, null, "private photo", new Error("private photo"),
    { code: "identical_pair", message: "private photo" },
    new EstimateError("unrecognized" as EstimateErrorCode),
  ])("does not reflect an unknown cause %#", (cause) => {
    expect(estimateErrorMessage(cause)).toBe(estimateErrorMessage(new EstimateError("unknown")));
    expect(estimateErrorMessage(cause)).not.toContain("private photo");
  });
});
