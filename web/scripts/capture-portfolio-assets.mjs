import { createHash } from "node:crypto";
import { lstat, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const arguments_ = process.argv.slice(2);

function option(name, fallback) {
  const index = arguments_.indexOf(name);
  if (index === -1) return fallback;
  const value = arguments_[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`Missing value for ${name}`);
  }
  return value;
}

const sourceUrl = option("--url", "http://127.0.0.1:4177/plategauge/");
const outputDirectory = resolve(
  option("--output", fileURLToPath(new URL("../../reports/media/", import.meta.url))),
);
const bundleDirectory = resolve(
  option("--bundle", fileURLToPath(new URL("../dist/", import.meta.url))),
);
const staticAuditPath = resolve(
  option(
    "--static-audit",
    fileURLToPath(new URL("../../reports/release/static-bundle-audit.json", import.meta.url)),
  ),
);

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function readJsonEvidence(path, label) {
  const bytes = await readFile(path);
  let payload;
  try {
    payload = JSON.parse(bytes.toString("utf8"));
  } catch (error) {
    throw new Error(`${label} is not valid JSON: ${error.message}`);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`${label} must contain a JSON object.`);
  }
  return { payload, sha256: sha256(bytes) };
}

async function currentBundleInventory(directory) {
  const entries = [];
  async function visit(relative) {
    const current = resolve(directory, relative);
    for (const entry of await readdir(current, { withFileTypes: true })) {
      const childRelative = relative ? `${relative}/${entry.name}` : entry.name;
      const child = resolve(directory, childRelative);
      const metadata = await lstat(child);
      if (metadata.isSymbolicLink()) {
        throw new Error(`Static bundle contains a symlink: ${childRelative}`);
      }
      if (metadata.isDirectory()) {
        await visit(childRelative);
      } else if (metadata.isFile()) {
        const bytes = await readFile(child);
        entries.push([childRelative.replaceAll("\\", "/"), sha256(bytes)]);
      }
    }
  }
  await visit("");
  entries.sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
  const hashes = Object.fromEntries(entries);
  return {
    fileCount: entries.length,
    inventorySha256: sha256(Buffer.from(JSON.stringify(hashes), "utf8")),
  };
}

async function loadCaptureProvenance() {
  const staticAudit = await readJsonEvidence(staticAuditPath, "static bundle audit");
  if (
    staticAudit.payload.kind !== "static_release_bundle_audit" ||
    staticAudit.payload.status !== "passed"
  ) {
    throw new Error("Static bundle audit is absent or not passing.");
  }
  const currentInventory = await currentBundleInventory(bundleDirectory);
  const inventorySha256 = staticAudit.payload.inventorySha256;
  const modelSha256 = staticAudit.payload.model?.sha256;
  if (
    typeof inventorySha256 !== "string" ||
    !/^[a-f0-9]{64}$/u.test(inventorySha256) ||
    typeof modelSha256 !== "string" ||
    !/^[a-f0-9]{64}$/u.test(modelSha256)
  ) {
    throw new Error("Static bundle audit lacks canonical inventory/model hashes.");
  }
  if (
    currentInventory.inventorySha256 !== inventorySha256 ||
    currentInventory.fileCount !== staticAudit.payload.fileCount
  ) {
    throw new Error("The current web/dist inventory differs from the canonical static audit.");
  }
  const modelBytes = await readFile(resolve(bundleDirectory, "models/plategauge.onnx"));
  if (sha256(modelBytes) !== modelSha256) {
    throw new Error("The current bundled model differs from the canonical static audit.");
  }
  return {
    generatedDate: new Date().toISOString().slice(0, 10),
    modelSha256,
    productionInventorySha256: inventorySha256,
    staticBundleAuditVerified: true,
    staticBundleAuditSha256: staticAudit.sha256,
  };
}

if (!/^https?:\/\/127\.0\.0\.1(?::\d+)?\//u.test(sourceUrl)) {
  throw new Error("Review capture is restricted to a local 127.0.0.1 preview URL.");
}

await mkdir(outputDirectory, { recursive: true });
const captureProvenance = await loadCaptureProvenance();

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
  colorScheme: "light",
  reducedMotion: "reduce",
});

const captures = [];

async function captureElement(filename, selector, description) {
  const locator = page.locator(selector);
  await locator.scrollIntoViewIfNeeded();
  await locator.screenshot({
    path: resolve(outputDirectory, filename),
    animations: "disabled",
  });
  captures.push({ filename, description, selector });
}

try {
  await page.goto(sourceUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { level: 1 }).waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
  // Fixed/sticky navigation is useful in the live page but obscures the top of
  // tall element screenshots when Chromium stitches them. This capture-only
  // override leaves the application unchanged and keeps each section complete.
  await page.addStyleTag({
    content: ".skip-link{display:none!important}.site-header{position:static!important}",
  });

  await captureElement(
    "01-question-and-boundary.png",
    "#top",
    "Benchmark question, primary negative finding, and non-estimator boundary.",
  );
  await captureElement(
    "02-frozen-results.png",
    "#results",
    "Frozen paired-versus-after-only result and release-gate summary.",
  );
  await captureElement(
    "03-selected-success.png",
    "#explorer",
    "Disclosed close-error benchmark example with both model comparisons.",
  );
  await page.screenshot({
    path: resolve(outputDirectory, "plategauge-full-page-review.png"),
    animations: "disabled",
    fullPage: true,
  });
  captures.push({
    filename: "plategauge-full-page-review.png",
    description: "Full local review page with the default disclosed success selected.",
    selector: "full page",
  });

  const failureButton = page.locator(".chooser-group").nth(1).locator("button").first();
  await failureButton.click();
  await page.locator("#selected-example-title").waitFor({ state: "visible" });
  await captureElement(
    "04-largest-failure.png",
    "#explorer",
    "Disclosed large-error benchmark example with limitations visible.",
  );
  await captureElement(
    "05-category-shift-method.png",
    "#method",
    "Frozen category-disjoint method and honest comparison design.",
  );

  const limits = page.locator("#limits");
  const attribution = page.locator(".attribution-section");
  await limits.scrollIntoViewIfNeeded();
  const limitsBox = await limits.boundingBox();
  const attributionBox = await attribution.boundingBox();
  if (!limitsBox || !attributionBox) {
    throw new Error("Could not measure the limits/attribution capture region.");
  }
  const lowerBoundary = attributionBox.y + attributionBox.height;
  const clip = {
    x: 0,
    y: Math.max(0, limitsBox.y),
    width: 1440,
    height: lowerBoundary - Math.max(0, limitsBox.y),
  };
  await page.screenshot({
    path: resolve(outputDirectory, "06-limits-and-attribution.png"),
    animations: "disabled",
    clip,
  });
  captures.push({
    filename: "06-limits-and-attribution.png",
    description: "Unsupported claims, external-validity boundary, and LeFood attribution.",
    selector: "#limits + .attribution-section",
  });

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto(sourceUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { level: 1 }).waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
  const heroBox = await page.locator("#top").boundingBox();
  if (!heroBox) throw new Error("Could not measure the social-preview hero region.");
  await page.screenshot({
    path: resolve(outputDirectory, "plategauge-social-preview-1280x640.png"),
    animations: "disabled",
    clip: { x: 0, y: heroBox.y, width: 1280, height: 640 },
  });
  captures.push({
    filename: "plategauge-social-preview-1280x640.png",
    description: "GitHub-compatible social preview from the exact local candidate.",
    selector: "#top (1280x640 crop)",
  });
} finally {
  await browser.close();
}

const files = [];
for (const capture of captures) {
  const bytes = await readFile(resolve(outputDirectory, capture.filename));
  files.push({
    ...capture,
    bytes: bytes.byteLength,
    sha256: createHash("sha256").update(bytes).digest("hex"),
  });
}

const manifest = {
  schemaVersion: 1,
  status: "LOCAL_REVIEW_DRAFT_NOT_RELEASED",
  generatedDate: captureProvenance.generatedDate,
  source: {
    productForm: "benchmark_failure_explorer",
    localPreviewUrl: "redacted; capture restricted to 127.0.0.1",
    modelSha256: captureProvenance.modelSha256,
    productionInventorySha256: captureProvenance.productionInventorySha256,
    staticBundleAuditVerified: captureProvenance.staticBundleAuditVerified,
    staticBundleAuditSha256: captureProvenance.staticBundleAuditSha256,
  },
  files,
  boundaries: [
    "Generated from the exact local benchmark/failure-explorer build.",
    "No arbitrary-image estimator or new numeric result is shown.",
    "Bundled LeFood example images retain the repository NOTICE and CC BY 4.0 attribution.",
    "These files are review assets, not evidence of release approval or deployment.",
  ],
};

await writeFile(
  resolve(outputDirectory, "portfolio-media-manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

console.log(JSON.stringify({ outputDirectory, files }, null, 2));
