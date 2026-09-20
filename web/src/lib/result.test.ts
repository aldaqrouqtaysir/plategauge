import { describe, expect, it } from "vitest";
import type { RawQuantiles } from "../types";
import {
  createPlateGaugeResult,
  formatGrams,
  formatPercent,
  parseStartingMass,
} from "./result";

const quantiles: RawQuantiles = {
  q05: 0.3,
  q50: 0.4,
  q95: 0.5,
  modelVersion: "v1",
  intervalGatePassed: true,
  abstentionWidth: 0.3,
  isTestAdapter: false,
  processingMs: 12.4,
};

describe("parseStartingMass", () => {
  it("allows omission and parses a valid mass", () => {
    expect(parseStartingMass("  ")).toBeUndefined();
    expect(parseStartingMass("320.5")).toBe(320.5);
  });

  it.each(["0", "-1", "Infinity", "not a number", "100001"])(
    "rejects invalid mass %s",
    (value) => expect(() => parseStartingMass(value)).toThrow(/Starting mass/),
  );
});

describe("createPlateGaugeResult", () => {
  it("creates an estimate with empirical and mass intervals", () => {
    expect(createPlateGaugeResult(quantiles, 200)).toMatchObject({
      status: "estimate",
      leftoverFraction: 0.4,
      empiricalInterval90: [0.3, 0.5],
      remainingMassG: 80,
      remainingMassIntervalG: [60, 100],
    });
  });

  it("withholds an interval that has not passed the release gate", () => {
    const result = createPlateGaugeResult(
      { ...quantiles, intervalGatePassed: false, isTestAdapter: true },
      undefined,
    );
    expect(result).toMatchObject({ status: "estimate", leftoverFraction: 0.4 });
    if (result.status === "estimate") {
      expect(result.empiricalInterval90).toBeUndefined();
      expect(result.remainingMassG).toBeUndefined();
      expect(result.warnings.join(" ")).toMatch(/withheld.*Test-only/i);
    }
  });

  it("abstains instead of leaking a numeric estimate", () => {
    const result = createPlateGaugeResult(
      { ...quantiles, q05: 0.1, q95: 0.7, abstentionWidth: 0.3 },
      200,
    );
    expect(result.status).toBe("abstain");
    if (result.status === "abstain") {
      expect(result.modelVersion).toBe("v1");
      expect(result.reasonCodes).toEqual(["UNCERTAINTY_TOO_WIDE"]);
      expect(result.warnings.some((warning) => /too uncertain/i.test(warning))).toBe(true);
    }
  });
});

describe("formatters", () => {
  it("formats percentages and grams for display", () => {
    expect(formatPercent(0.425)).toMatch(/42\.5/);
    expect(formatGrams(80.25)).toMatch(/80\.3 g/);
  });
});
