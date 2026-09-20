import {
  absoluteError,
  benchmarkSemantics,
  benchmarkEvidenceProvenance,
  benchmarkExamples,
  categoryComparisons,
  engineeringEvidence,
  endpointPrevalence,
  exampleAssetUrl,
  frozenMetrics,
  robustnessSummary,
  targetSliceMetrics,
  workloadEvidence,
} from "./benchmarkData";

describe("frozen benchmark explorer data", () => {
  it("is bound to the frozen canonical source inventory", () => {
    expect(benchmarkEvidenceProvenance.kind).toBe("derived_frozen_web_benchmark_evidence");
    expect(benchmarkEvidenceProvenance.protocolId).toHaveLength(64);
    expect(Object.keys(benchmarkEvidenceProvenance.sourceFiles)).toHaveLength(18);
    expect(benchmarkEvidenceProvenance.sourceFiles["reports/results.json"]).toMatch(
      /^[a-f0-9]{64}$/,
    );
    expect(
      benchmarkEvidenceProvenance.sourceFiles[
        "reports/experiments/confirmatory/tasks/outer.fold-4.paired_mobilenet/workload/predictions.csv"
      ],
    ).toMatch(/^[a-f0-9]{64}$/);
    expect(benchmarkEvidenceProvenance.sourceFiles["reports/robustness.json"]).toMatch(
      /^[a-f0-9]{64}$/,
    );
  });

  it("contains five disclosed representative successes and five largest errors", () => {
    expect(benchmarkExamples.filter((item) => item.kind === "representative_success")).toHaveLength(5);
    expect(benchmarkExamples.filter((item) => item.kind === "largest_error")).toHaveLength(5);
    expect(new Set(benchmarkExamples.map((item) => item.id)).size).toBe(10);
  });

  it("keeps fractions bounded and computed labels consistent", () => {
    for (const example of benchmarkExamples) {
      expect(example.target).toBeCloseTo(example.afterMassG / example.beforeMassG, 12);
      expect(example.target).toBeGreaterThanOrEqual(0);
      expect(example.target).toBeLessThanOrEqual(1);
      expect(example.pairedPrediction).toBeGreaterThanOrEqual(0);
      expect(example.pairedPrediction).toBeLessThanOrEqual(1);
      expect(example.afterOnlyPrediction).toBeGreaterThanOrEqual(0);
      expect(example.afterOnlyPrediction).toBeLessThanOrEqual(1);
    }
  });

  it("orders the five error examples by descending frozen error", () => {
    const failures = benchmarkExamples.filter((item) => item.kind === "largest_error");
    expect(failures.map((item) => item.rank)).toEqual([1, 2, 3, 4, 5]);
    const errors = failures.map((item) => absoluteError(item.pairedPrediction, item.target));
    expect(errors).toEqual([...errors].sort((left, right) => right - left));
  });

  it("preserves the frozen negative comparison", () => {
    expect(frozenMetrics.pairedMacroMae).toBeGreaterThan(frozenMetrics.afterOnlyMacroMae);
    expect(frozenMetrics.pairedMacroMae - frozenMetrics.afterOnlyMacroMae).toBeCloseTo(
      frozenMetrics.pairedMinusAfterOnly,
      14,
    );
  });

  it("exposes all model/control workloads and the contextual observer reference", () => {
    expect(workloadEvidence.modelAndControlWorkloadCount).toBe(7);
    expect(workloadEvidence.contextualReferenceCount).toBe(1);
    expect(workloadEvidence.records).toHaveLength(8);
    expect(workloadEvidence.records.map((record) => record.macroCategoryMae)).toEqual(
      [...workloadEvidence.records]
        .sort((left, right) => left.macroCategoryMae - right.macroCategoryMae)
        .map((record) => record.macroCategoryMae),
    );
    const observer = workloadEvidence.records.find(
      (record) => record.id === "observer_score_context_only",
    );
    const wrongPair = workloadEvidence.records.find(
      (record) => record.id === "fixed_within_category_wrong_pair",
    );
    expect(observer?.role).toBe("contextual_reference");
    expect(observer?.caveat).toContain("not a deployable model");
    expect(wrongPair?.role).toBe("destructive_mismatch_control");
    expect(wrongPair?.caveat).toContain("not evidence that the before image adds predictive value");
  });

  it("binds category, endpoint, and robustness evidence", () => {
    expect(categoryComparisons).toHaveLength(34);
    expect(categoryComparisons.reduce((total, record) => total + record.support, 0)).toBe(514);
    expect(endpointPrevalence).toMatchObject({
      exactZero: 207,
      exactOne: 47,
      interior: 260,
      endpointTotal: 254,
      total: 514,
    });
    expect(robustnessSummary.downgradeRequired).toBe(true);
    expect(
      robustnessSummary.records.find(
        (record) => record.id === "after_gaussian_blur_sigma_1",
      ),
    ).toMatchObject({
      deltaFromClean: 0.034532527658502635,
      downgradeThreshold: 0.03,
      thresholdBreached: true,
    });
    expect(benchmarkSemantics.target).toContain("0 means none left and 1 means all left");
  });

  it("preserves the frozen target-slice and engineering evidence", () => {
    expect(targetSliceMetrics.reduce((total, slice) => total + slice.count, 0)).toBe(
      frozenMetrics.validPairs,
    );
    expect(Math.max(...targetSliceMetrics.map((slice) => slice.microMae))).toBeCloseTo(
      frozenMetrics.worstBroadTargetSliceMicroMae,
      5,
    );
    expect(engineeringEvidence.modelBytes).toBe(10_355_122);
    expect(engineeringEvidence.maximumPytorchOnnxDrift).toBe(5.185604095458984e-6);
    expect(engineeringEvidence.warmP95Ms).toBe(22.119999885559082);
    expect(engineeringEvidence.peakMemoryMiB).toBe(45.64192485809326);
  });

  it("builds base-aware same-origin asset paths", () => {
    expect(exampleAssetUrl("lefood-0192", "before")).toMatch(
      /\/examples\/lefood-0192-before\.jpg$/,
    );
  });
});
