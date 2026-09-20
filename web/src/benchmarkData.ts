import generatedEvidence from "./generated/benchmarkEvidence.json";

export type BenchmarkExampleKind = "representative_success" | "largest_error";

export interface BenchmarkExample {
  id: string;
  kind: BenchmarkExampleKind;
  rank: number;
  foodName: string;
  category: string;
  fold: number;
  beforeMassG: number;
  afterMassG: number;
  target: number;
  pairedPrediction: number;
  afterOnlyPrediction: number;
  note: string;
}

function benchmarkKind(value: string): BenchmarkExampleKind {
  if (value === "representative_success" || value === "largest_error") {
    return value;
  }
  throw new Error(`Unsupported generated benchmark example kind: ${value}`);
}

export const benchmarkEvidenceProvenance = generatedEvidence.provenance;
export const frozenMetrics = generatedEvidence.frozenMetrics;
export const workloadEvidence = generatedEvidence.workloadEvidence;
export const categoryComparisons = generatedEvidence.categoryComparisons;
export const targetSliceMetrics = generatedEvidence.targetSliceMetrics;
export const endpointPrevalence = generatedEvidence.endpointPrevalence;
export const robustnessSummary = generatedEvidence.robustnessSummary;
export const engineeringEvidence = generatedEvidence.engineeringEvidence;
export const benchmarkSemantics = generatedEvidence.semantics;

/**
 * Generated from frozen outer-fold predictions, the LeFood manifest, and the
 * reviewed error evidence. CI regenerates the payload and fails if any
 * browser-visible value diverges from those canonical sources.
 */
export const benchmarkExamples: readonly BenchmarkExample[] =
  generatedEvidence.benchmarkExamples.map((example) => ({
    ...example,
    kind: benchmarkKind(example.kind),
  }));

export function exampleAssetUrl(exampleId: string, role: "before" | "after"): string {
  return `${import.meta.env.BASE_URL}examples/${exampleId}-${role}.jpg`;
}

export function absoluteError(prediction: number, target: number): number {
  return Math.abs(prediction - target);
}
