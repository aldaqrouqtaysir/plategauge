import { describe, expect, it } from "vitest";
import { parseReleaseManifest } from "./releaseManifest";

const validManifest = {
  schemaVersion: 1,
  modelVersion: "v1.0.0",
  modelPath: "models/plategauge.onnx",
  modelSha256: "a".repeat(64),
  beforeInputName: "before",
  afterInputName: "after",
  outputName: "quantiles",
  calibration: {
    lowerExpansion: 0.02,
    upperExpansion: 0.03,
    abstentionWidth: 0.3,
    intervalGatePassed: false,
  },
};

describe("parseReleaseManifest", () => {
  it("accepts the frozen release schema", () => {
    expect(parseReleaseManifest(validManifest)).toEqual(validManifest);
  });

  it.each([
    null,
    {},
    { ...validManifest, schemaVersion: 2 },
    { ...validManifest, modelVersion: "" },
    { ...validManifest, modelPath: "../other/model.onnx" },
    { ...validManifest, modelPath: "https://example.com/model.onnx" },
    { ...validManifest, modelPath: "models/model.pt" },
    { ...validManifest, modelSha256: "not-a-hash" },
    { ...validManifest, beforeInputName: "before input" },
    { ...validManifest, afterInputName: [] },
    { ...validManifest, outputName: "" },
    { ...validManifest, calibration: null },
    { ...validManifest, calibration: { ...validManifest.calibration, lowerExpansion: -1 } },
    { ...validManifest, calibration: { ...validManifest.calibration, upperExpansion: 2 } },
    { ...validManifest, calibration: { ...validManifest.calibration, abstentionWidth: 0 } },
    { ...validManifest, calibration: { ...validManifest.calibration, intervalGatePassed: "yes" } },
  ])("rejects invalid or unsafe manifests", (candidate) => {
    expect(parseReleaseManifest(candidate)).toBeNull();
  });
});
