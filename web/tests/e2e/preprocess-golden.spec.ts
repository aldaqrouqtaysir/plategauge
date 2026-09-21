import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { verifyUniformPreprocess } from "../support/uniformPreprocess";

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
  rgbaBase64: string;
  tensorBase64: string;
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

test("preprocessing preserves exact goldens with bounded WebKit resize compatibility", async ({ page, browserName }, testInfo) => {
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
    await testInfo.attach(`${fixture.fixture_id}-observation.json`, {
      body: JSON.stringify(actual),
      contentType: "application/json",
    });
    const uniformColors: Record<string, readonly [number, number, number]> = {
      landscape_uniform: [17, 101, 233],
      portrait_uniform: [201, 77, 31],
    };
    const color = uniformColors[fixture.fixture_id];
    if (browserName === "webkit" && color) {
      const comparison = verifyUniformPreprocess(
        Buffer.from(actual.rgbaBase64, "base64"),
        Buffer.from(actual.tensorBase64, "base64"),
        color,
      );
      await testInfo.attach(`${fixture.fixture_id}-compatibility.json`, {
        body: JSON.stringify(comparison),
        contentType: "application/json",
      });
    } else {
      expect(actual.rgbaSha256, fixture.fixture_id).toBe(fixture.expected_rgba_sha256);
      expect(actual.tensorSha256, fixture.fixture_id).toBe(
        fixture.expected_normalized_chw_float32_sha256,
      );
    }
  }
});
