import type { PlateGaugeResult, RawQuantiles } from "../types";

export const MAX_STARTING_MASS_G = 100_000;

export function parseStartingMass(raw: string): number | undefined {
  if (raw.trim() === "") return undefined;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0 || value > MAX_STARTING_MASS_G) {
    throw new Error("Starting mass must be greater than 0 and no more than 100,000 grams.");
  }
  return value;
}

export function createPlateGaugeResult(
  quantiles: RawQuantiles,
  startingMassG?: number,
): PlateGaugeResult {
  const intervalWidth = quantiles.q95 - quantiles.q05;
  if (intervalWidth > quantiles.abstentionWidth) {
    return {
      status: "abstain",
      modelVersion: quantiles.modelVersion,
      reasonCodes: ["UNCERTAINTY_TOO_WIDE"],
      warnings: [
        "The model was too uncertain for this image pair, so no numeric estimate is shown.",
        "Try photographs with the same container, angle, distance, and lighting.",
      ],
    };
  }

  const interval = quantiles.intervalGatePassed
    ? ([quantiles.q05, quantiles.q95] satisfies [number, number])
    : undefined;
  const warnings = [
    "Research demonstrator: this estimate does not replace a scale.",
    "Any measured performance is limited to the frozen benchmark and capture conditions documented in the model card.",
  ];
  if (!interval) {
    warnings.push("The empirical interval is withheld until its frozen release gate passes.");
  }
  if (quantiles.isTestAdapter) {
    warnings.push("Test-only deterministic adapter — not a trained model prediction.");
  }

  return {
    status: "estimate",
    modelVersion: quantiles.modelVersion,
    leftoverFraction: quantiles.q50,
    ...(interval ? { empiricalInterval90: interval } : {}),
    ...(startingMassG === undefined
      ? {}
      : {
          remainingMassG: quantiles.q50 * startingMassG,
          ...(interval
            ? {
                remainingMassIntervalG: [
                  interval[0] * startingMassG,
                  interval[1] * startingMassG,
                ] satisfies [number, number],
              }
            : {}),
        }),
    warnings,
    processingMs: quantiles.processingMs,
  };
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat("en", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatGrams(value: number): string {
  return `${new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(value)} g`;
}
