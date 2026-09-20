#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { cpus, hostname, platform, release, totalmem, type as osType, arch } from "node:os";
import { dirname, extname, join, normalize, resolve, sep } from "node:path";
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const FIXED_BENCHMARK_SAMPLE_ID = "lefood-0192";
const SHA256_PATTERN = /^[a-f0-9]{64}$/;

export function parseArguments(values) {
  const options = { headless: false };
  const valueOptions = new Set([
    "--web-root",
    "--base-path",
    "--warmups",
    "--measurements",
    "--browser-channel",
  ]);
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index];
    if (key === "--headless") {
      options.headless = true;
      continue;
    }
    if (!key?.startsWith("--")) throw new Error(`Unexpected argument: ${key ?? "<missing>"}`);
    if (!valueOptions.has(key)) throw new Error(`Unexpected argument: ${key}`);
    const value = values[index + 1];
    if (value === undefined || value.startsWith("--")) throw new Error(`Missing value for ${key}`);
    options[key.slice(2)] = value;
    index += 1;
  }
  const required = [
    "web-root",
    "base-path",
    "warmups",
    "measurements",
    "browser-channel",
  ];
  for (const key of required) {
    if (typeof options[key] !== "string" || options[key].length === 0) {
      throw new Error(`Missing required --${key}`);
    }
  }
  const warmups = Number.parseInt(options.warmups, 10);
  const measurements = Number.parseInt(options.measurements, 10);
  if (!Number.isInteger(warmups) || warmups < 3) throw new Error("warmups must be at least 3");
  if (!Number.isInteger(measurements) || measurements < 20) {
    throw new Error("measurements must be at least 20");
  }
  if (!["chrome", "msedge", "chromium"].includes(options["browser-channel"])) {
    throw new Error("browser-channel must be chrome, msedge, or chromium");
  }
  let basePath = options["base-path"];
  if (!basePath.startsWith("/") || basePath.includes("..")) {
    throw new Error("base-path must be absolute and traversal-free");
  }
  if (!basePath.endsWith("/")) basePath += "/";
  return {
    webRoot: resolve(options["web-root"]),
    basePath,
    warmups,
    measurements,
    browserChannel: options["browser-channel"],
    headless: options.headless,
  };
}

function contentType(path) {
  return (
    {
      ".css": "text/css; charset=utf-8",
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".json": "application/json; charset=utf-8",
      ".mjs": "text/javascript; charset=utf-8",
      ".onnx": "application/octet-stream",
      ".png": "image/png",
      ".svg": "image/svg+xml",
      ".wasm": "application/wasm",
      ".webp": "image/webp",
    }[extname(path).toLowerCase()] ?? "application/octet-stream"
  );
}

async function startStaticServer(webRoot, basePath) {
  let transferredBodyBytes = 0;
  const rootPrefix = `${resolve(webRoot)}${sep}`;
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://127.0.0.1");
      if (!url.pathname.startsWith(basePath)) {
        response.writeHead(404).end("Not found");
        return;
      }
      let relative = decodeURIComponent(url.pathname.slice(basePath.length));
      if (relative === "" || relative.endsWith("/")) relative += "index.html";
      const candidate = resolve(webRoot, normalize(relative));
      if (candidate !== resolve(webRoot) && !candidate.startsWith(rootPrefix)) {
        response.writeHead(400).end("Invalid path");
        return;
      }
      let details;
      try {
        details = await stat(candidate);
      } catch {
        response.writeHead(404).end("Not found");
        return;
      }
      if (!details.isFile()) {
        response.writeHead(404).end("Not found");
        return;
      }
      const body = await readFile(candidate);
      transferredBodyBytes += body.byteLength;
      response.writeHead(200, {
        "Cache-Control": "no-store",
        "Content-Length": String(body.byteLength),
        "Content-Type": contentType(candidate),
        "Cross-Origin-Embedder-Policy": "require-corp",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
      });
      response.end(body);
    } catch (error) {
      response.writeHead(500).end(error instanceof Error ? error.message : "Server error");
    }
  });
  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(0, "127.0.0.1", resolveListen);
  });
  const address = server.address();
  if (address === null || typeof address === "string") throw new Error("Local server has no port");
  return {
    url: `http://127.0.0.1:${address.port}${basePath}`,
    transferredBytes: () => transferredBodyBytes,
    close: () => new Promise((resolveClose, rejectClose) => {
      server.close((error) => (error ? rejectClose(error) : resolveClose()));
    }),
  };
}

function windowsManufacturerModel() {
  if (platform() !== "win32") return null;
  try {
    const command = [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      "Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model | ConvertTo-Json -Compress",
    ];
    const raw = execFileSync("powershell.exe", command, { encoding: "utf8", timeout: 15_000 });
    const value = JSON.parse(raw);
    const manufacturer = String(value.Manufacturer ?? "").trim();
    const model = String(value.Model ?? "").trim();
    return `${manufacturer} ${model}`.trim() || null;
  } catch {
    return null;
  }
}

async function runtimeVersion() {
  const packagePath = join(SCRIPT_DIRECTORY, "..", "node_modules", "onnxruntime-web", "package.json");
  const value = JSON.parse(await readFile(packagePath, "utf8"));
  if (typeof value.version !== "string" || value.version.length === 0) {
    throw new Error("Cannot determine the installed onnxruntime-web version");
  }
  return value.version;
}

async function sampleApplicationMemory(page) {
  const result = await page.evaluate(async () => {
    const candidate = performance.measureUserAgentSpecificMemory;
    if (!crossOriginIsolated) {
      return { error: "page is not cross-origin isolated" };
    }
    if (typeof candidate !== "function") {
      return { error: "performance.measureUserAgentSpecificMemory is unavailable" };
    }
    try {
      const measurement = await candidate.call(performance);
      return { bytes: measurement.bytes };
    } catch (error) {
      return { error: error instanceof Error ? error.message : "memory API failed" };
    }
  });
  if (typeof result.bytes !== "number" || !Number.isFinite(result.bytes) || result.bytes <= 0) {
    throw new Error(
      `Reliable application memory measurement unavailable: ${result.error ?? "invalid byte count"}`,
    );
  }
  return result.bytes;
}

async function runFixedInference(page, expected) {
  const runButton = page.getByTestId("run-fixed-example");
  if ((await runButton.getAttribute("data-sample-id")) !== expected.sampleId) {
    throw new Error("Fixed replay button is bound to an unexpected sample");
  }
  if (await runButton.isDisabled()) {
    throw new Error("Fixed replay button is disabled after model and asset readiness");
  }
  const priorCount = await page.evaluate(() => window.__plateGaugeBenchmarkTimings.length);
  await runButton.click();
  await page.waitForFunction(
    (count) => window.__plateGaugeBenchmarkTimings.length > count,
    priorCount,
    { timeout: 120_000 },
  );
  const output = page.getByTestId("runtime-output");
  await output.waitFor({ state: "visible", timeout: 120_000 });
  const timing = await page.evaluate(() => window.__plateGaugeBenchmarkTimings.at(-1));
  if (typeof timing !== "number" || !Number.isFinite(timing) || timing <= 0) {
    throw new Error("Browser worker returned an invalid inference duration");
  }
  const outputSampleId = await output.getAttribute("data-sample-id");
  const outputModelVersion = await output.getAttribute("data-model-version");
  const outputTestAdapter = await output.getAttribute("data-test-adapter");
  const outputTiming = Number.parseFloat(
    (await output.getAttribute("data-processing-ms")) ?? "",
  );
  if (
    outputSampleId !== expected.sampleId ||
    outputModelVersion !== expected.modelVersion ||
    outputTestAdapter !== "false"
  ) {
    throw new Error("Fixed replay output identity differs from the ready harness");
  }
  if (!Number.isFinite(outputTiming) || Math.abs(outputTiming - timing) > 0.001) {
    throw new Error("Rendered worker duration differs from the captured worker message");
  }
  return timing;
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  const server = await startStaticServer(options.webRoot, options.basePath);
  let browser;
  try {
    browser = await chromium.launch({
      channel: options.browserChannel === "chromium" ? undefined : options.browserChannel,
      headless: options.headless,
    });
    const context = await browser.newContext({ serviceWorkers: "block" });
    await context.addInitScript(() => {
      Object.defineProperty(window, "__plateGaugeBenchmarkTimings", {
        configurable: false,
        value: [],
        writable: false,
      });
      const OriginalWorker = window.Worker;
      window.Worker = new Proxy(OriginalWorker, {
        construct(target, argumentsList) {
          const worker = Reflect.construct(target, argumentsList);
          worker.addEventListener("message", (event) => {
            const value = event.data;
            if (
              value?.type === "result" &&
              typeof value.result?.processingMs === "number" &&
              Number.isFinite(value.result.processingMs)
            ) {
              window.__plateGaugeBenchmarkTimings.push(value.result.processingMs);
            }
          });
          return worker;
        },
      });
    });
    const page = await context.newPage();
    const measuredAt = new Date().toISOString();
    const benchmarkUrl = new URL(server.url);
    benchmarkUrl.searchParams.set("benchmark", "1");
    await page.goto(benchmarkUrl.toString(), { waitUntil: "networkidle", timeout: 120_000 });
    const ready = page.getByTestId("model-ready");
    await ready.waitFor({ state: "visible", timeout: 120_000 });
    const modelVersion = await ready.getAttribute("data-model-version");
    const testAdapter = await ready.getAttribute("data-test-adapter");
    if (typeof modelVersion !== "string" || modelVersion.length === 0 || testAdapter !== "false") {
      const readyText = (await ready.textContent()) ?? "";
      throw new Error(`The production model did not initialize: ${readyText.trim()}`);
    }
    const fixedReady = page.getByTestId("fixed-example-ready");
    await fixedReady.waitFor({ state: "visible", timeout: 120_000 });
    await page.waitForFunction(
      (sampleId) => {
        const element = document.querySelector('[data-testid="fixed-example-ready"]');
        return (
          element?.getAttribute("data-sample-id") === sampleId &&
          /^[a-f0-9]{64}$/.test(element.getAttribute("data-before-sha256") ?? "") &&
          /^[a-f0-9]{64}$/.test(element.getAttribute("data-after-sha256") ?? "") &&
          element.textContent?.includes("ready")
        );
      },
      FIXED_BENCHMARK_SAMPLE_ID,
      { timeout: 120_000 },
    );
    const fixedSampleId = await fixedReady.getAttribute("data-sample-id");
    const fixedBeforeSha256 = await fixedReady.getAttribute("data-before-sha256");
    const fixedAfterSha256 = await fixedReady.getAttribute("data-after-sha256");
    if (
      fixedSampleId !== FIXED_BENCHMARK_SAMPLE_ID ||
      !SHA256_PATTERN.test(fixedBeforeSha256 ?? "") ||
      !SHA256_PATTERN.test(fixedAfterSha256 ?? "")
    ) {
      throw new Error("The fixed benchmark pair identity or asset hashes are invalid");
    }
    const firstLoadBytes = server.transferredBytes();
    const memorySamples = [await sampleApplicationMemory(page)];
    const expectedReplay = { sampleId: fixedSampleId, modelVersion };

    for (let index = 0; index < options.warmups; index += 1) {
      await runFixedInference(page, expectedReplay);
      memorySamples.push(await sampleApplicationMemory(page));
    }
    const timings = [];
    for (let index = 0; index < options.measurements; index += 1) {
      timings.push(await runFixedInference(page, expectedReplay));
      memorySamples.push(await sampleApplicationMemory(page));
    }

    const cpu = cpus()[0]?.model?.trim();
    if (!cpu) throw new Error("Cannot determine the reference CPU");
    const manufacturerModel = windowsManufacturerModel() ?? `Unreported host model (${hostname()})`;
    const browserNames = { chrome: "Chrome", msedge: "Microsoft Edge", chromium: "Chromium" };
    const observation = {
      schema_version: "1.1",
      kind: "physical_browser_observation",
      measured_at: measuredAt,
      browser_name: browserNames[options.browserChannel],
      browser_version: browser.version(),
      browser_mode: options.headless ? "headless" : "headed",
      onnxruntime_web_version: await runtimeVersion(),
      manufacturer_model: manufacturerModel,
      cpu,
      ram_gb: totalmem() / 1024 ** 3,
      operating_system: `${osType()} ${release()} (${arch()})`,
      warmup_runs: options.warmups,
      warm_inference_ms: timings,
      first_load_bytes: firstLoadBytes,
      peak_application_memory_mb: Math.max(...memorySamples) / 1024 ** 2,
      memory_measurement_method: "performance.measureUserAgentSpecificMemory",
      memory_measurement_notes:
        `Maximum of ${memorySamples.length} application-memory samples: one after model ` +
        "initialization and one after every warmup/measured inference; cross-origin-isolated " +
        "local static build; browser API bytes converted to MiB. First-load bytes are the " +
        "sum of no-store response-body bytes served through model and fixed-pair readiness " +
        "(HTTP headers excluded).",
      fixed_sample_id: fixedSampleId,
      fixed_before_sha256: fixedBeforeSha256,
      fixed_after_sha256: fixedAfterSha256,
      numeric_prediction_recorded: false,
    };
    process.stdout.write(`${JSON.stringify(observation)}\n`);
    await context.close();
  } finally {
    if (browser) await browser.close();
    await server.close();
  }
}

const executedDirectly =
  typeof process.argv[1] === "string" &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (executedDirectly) {
  main().catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${JSON.stringify({ status: "blocked", error: message })}\n`);
    process.exitCode = 2;
  });
}
