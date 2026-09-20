import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

interface GoldenFixture {
  fixture_id: string;
  source_file: string;
  expected_rgba_sha256: string;
  expected_normalized_chw_float32_sha256: string;
  geometry: {
    resized_width: number;
    resized_height: number;
    crop_left: number;
    crop_top: number;
  };
}

interface GoldenManifest {
  fixtures: GoldenFixture[];
}

interface BrowserGoldenResult {
  geometry: {
    resizedWidth: number;
    resizedHeight: number;
    cropLeft: number;
    cropTop: number;
  };
  rgbaSha256: string;
  tensorSha256: string;
}

declare global {
  interface Window {
    __plateGaugePreprocessGolden?: (file: File) => Promise<BrowserGoldenResult>;
  }
}

const fixtureRoot = new URL("../fixtures/preprocess-golden/", import.meta.url);
const manifest = JSON.parse(
  readFileSync(fileURLToPath(new URL("manifest.json", fixtureRoot)), "utf8"),
) as GoldenManifest;

test("browser preprocessing exactly matches the Python golden fixtures", async ({ page }) => {
  await page.goto("/");
  for (const fixture of manifest.fixtures) {
    const encoded = readFileSync(
      fileURLToPath(new URL(fixture.source_file, fixtureRoot)),
    ).toString("base64");
    const actual = await page.evaluate(({ base64 }) => {
      const bytes = Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
      const file = new File([bytes], "golden.png", { type: "image/png" });
      const harness = window.__plateGaugePreprocessGolden;
      if (!harness) throw new Error("Preprocessing golden harness is unavailable in test mode.");
      return harness(file);
    }, { base64: encoded });
    expect(actual.geometry.resizedWidth, fixture.fixture_id).toBe(
      fixture.geometry.resized_width,
    );
    expect(actual.geometry.resizedHeight, fixture.fixture_id).toBe(
      fixture.geometry.resized_height,
    );
    expect(actual.geometry.cropLeft, fixture.fixture_id).toBe(fixture.geometry.crop_left);
    expect(actual.geometry.cropTop, fixture.fixture_id).toBe(fixture.geometry.crop_top);
    expect(actual.rgbaSha256, fixture.fixture_id).toBe(fixture.expected_rgba_sha256);
    expect(actual.tensorSha256, fixture.fixture_id).toBe(
      fixture.expected_normalized_chw_float32_sha256,
    );
  }
});
