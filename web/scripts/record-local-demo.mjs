import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import { mediaTimestamp, reserveMediaOutput } from "./media-output.mjs";

const arguments_ = process.argv.slice(2);

function option(name, fallback) {
  const index = arguments_.indexOf(name);
  if (index === -1) return fallback;
  const value = arguments_[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`Missing value for ${name}`);
  return value;
}

const sourceUrl = option("--url", "http://127.0.0.1:4177/plategauge/");
const requestedOutput = option("--output");
const repository = fileURLToPath(new URL("../../", import.meta.url));

if (!/^https?:\/\/127\.0\.0\.1(?::\d+)?\//u.test(sourceUrl)) {
  throw new Error("Demo recording is restricted to a local 127.0.0.1 preview URL.");
}

const outputDirectory = await reserveMediaOutput(requestedOutput, repository);
const temporaryVideoDirectory = resolve(outputDirectory, ".demo-video-tmp");
const outputVideo = resolve(outputDirectory, "plategauge-local-review-demo.webm");
const outputManifest = resolve(outputDirectory, "demo-video-manifest.json");
await mkdir(temporaryVideoDirectory);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  colorScheme: "light",
  reducedMotion: "reduce",
  recordVideo: { dir: temporaryVideoDirectory, size: { width: 1280, height: 720 } },
});
const blockedRequests = [];
await context.route("**/*", async (route) => {
  const requestUrl = new URL(route.request().url());
  const localHttp =
    (requestUrl.protocol === "http:" || requestUrl.protocol === "https:") &&
    requestUrl.hostname === "127.0.0.1";
  const nonNetworkUrl = ["about:", "blob:", "data:"].includes(requestUrl.protocol);
  if (!localHttp && !nonNetworkUrl) {
    blockedRequests.push(requestUrl.href);
    await route.abort("blockedbyclient");
    return;
  }
  await route.continue();
});
const page = await context.newPage();
const video = page.video();

async function setCaption(title, body) {
  await page.evaluate(
    ({ title_, body_ }) => {
      document.querySelector("#plategauge-demo-caption")?.remove();
      const caption = document.createElement("aside");
      caption.id = "plategauge-demo-caption";
      caption.setAttribute("aria-label", "Demo caption");
      Object.assign(caption.style, {
        position: "fixed",
        zIndex: "2147483647",
        left: "28px",
        right: "28px",
        bottom: "24px",
        padding: "14px 18px",
        border: "1px solid rgba(255,255,255,.28)",
        borderRadius: "14px",
        background: "rgba(14,31,29,.94)",
        color: "#fff",
        boxShadow: "0 12px 36px rgba(0,0,0,.26)",
        fontFamily: "Inter, Arial, sans-serif",
        lineHeight: "1.35",
        pointerEvents: "none",
      });
      caption.innerHTML = `<strong style="display:block;font-size:18px;margin-bottom:3px"></strong><span style="font-size:15px"></span><small style="float:right;margin-top:4px;color:#cfe9e3">LOCAL REVIEW · NOT DEPLOYED</small>`;
      caption.querySelector("strong").textContent = title_;
      caption.querySelector("span").textContent = body_;
      document.body.append(caption);
    },
    { title_: title, body_: body },
  );
}

async function show(selector, title, body, milliseconds) {
  await page.locator(selector).scrollIntoViewIfNeeded();
  await page.waitForTimeout(350);
  await setCaption(title, body);
  await page.waitForTimeout(milliseconds);
}

let recordingError;
try {
  await page.goto(sourceUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { level: 1 }).waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);

  await show(
    "#top",
    "Question and boundary",
    "A frozen benchmark asks whether standardized before-and-after images add value. It is not a scale replacement or waste-reduction claim.",
    7000,
  );
  await show(
    "#results",
    "The preregistered hypothesis failed",
    "Paired MobileNet macro-category MAE was 0.1228; the after-only ablation was better at 0.0979.",
    8500,
  );
  await show(
    "#explorer",
    "Inspect frozen examples",
    "The explorer distinguishes measured targets from fixed outer-fold predictions and exposes both models side by side.",
    7500,
  );

  const firstFailure = page.locator(".chooser-group").nth(1).locator("button").first();
  await firstFailure.click();
  await page.locator("#selected-example-title").waitFor({ state: "visible" });
  await show(
    "#explorer",
    "Do not hide the failures",
    "Large errors, target-range weaknesses, and failed uncertainty gates are part of the frozen candidate evidence record.",
    8000,
  );
  await show(
    "#engineering",
    "Artifact-specific engineering evidence",
    "The exact 10.36 MB FP32 ONNX candidate passed parity and one documented Chrome laptop performance check—not a phone or production claim.",
    7500,
  );
  await show(
    "#method",
    "Category-disjoint evaluation",
    "All 514 valid pairs were evaluated once across 34 held-out food categories; duplicate-linked cases remained together.",
    7500,
  );
  await show(
    "#limits",
    "Release decision",
    "Because the estimator gates failed, PlateGauge remains a benchmark and failure explorer with no visitor uploads or new estimates.",
    8000,
  );
  await show(
    ".attribution-section",
    "Provenance and attribution",
    "LeFood-Set v1 is used under CC BY 4.0. The controlled Indonesian hospital context does not establish wider validity.",
    6500,
  );
  if (blockedRequests.length > 0) {
    throw new Error(`Blocked non-local requests: ${[...new Set(blockedRequests)].join(", ")}`);
  }
} catch (error) {
  recordingError = error;
} finally {
  await page.close();
}

if (!video) throw new Error("Playwright did not create a video handle.");
if (!recordingError) await video.saveAs(outputVideo);
await context.close();
// Delete only Playwright's own recorded file; leave the fresh diagnostics
// directory (and every failed attempt) for the author to review explicitly.
if (!recordingError) await video.delete();
await browser.close();
if (recordingError) throw recordingError;

const bytes = await readFile(outputVideo);
const manifest = {
  schemaVersion: 1,
  status: "LOCAL_REVIEW_DRAFT_NOT_RELEASED",
  generatedDate: mediaTimestamp().slice(0, 10),
  sourceUrl: "redacted; recording restricted to 127.0.0.1",
  file: {
    name: "plategauge-local-review-demo.webm",
    bytes: bytes.byteLength,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    audio: false,
    format: "WebM",
  },
  boundaries: [
    "Captioned silent local walkthrough; no human narration or independent-reproduction claim.",
    "No arbitrary-image estimator or new numeric result is shown.",
    "Not evidence of release approval, deployment, or operational validity.",
  ],
};
await writeFile(outputManifest, `${JSON.stringify(manifest, null, 2)}\n`, { encoding: "utf8", flag: "wx" });

console.log(JSON.stringify({ outputVideo, outputManifest, ...manifest.file }, null, 2));
