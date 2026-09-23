import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { expect, type BrowserContext, type Page } from "@playwright/test";

export const MODEL_SHA256 = "9c830e80cab86acd85c5b27b5733126594561844d0398d602a039c68befbd675";
export const MODEL_VERSION = "v1.0.0-paired-baseline/experimental-camera-r1";
export const BASE = "/plategauge/";
export interface CameraAudit {
  requests: MediaStreamConstraints[];
  behavior: "success" | "denied" | "pending";
  resolvePending: () => void;
  tracks: Array<{ ended: boolean }>;
  frames: number;
  workerStarts: number;
  workerStops: number;
  storageWrites: number;
  databaseCalls: number;
  uploads: number;
  createdUrls: string[];
  revokedUrls: string[];
}
export type AuditWindow = Window & { candidateAudit: CameraAudit; candidateLifecycle: (kind: string, value: string) => Promise<void> };
export interface Lifecycle { stopped: string[]; created: string[]; revoked: string[] }

/** Completely replaces getUserMedia before application code: no hardware path exists. */
export async function installCamera(page: Page): Promise<Lifecycle> {
  const lifecycle: Lifecycle = { stopped: [], created: [], revoked: [] };
  await page.exposeFunction("candidateLifecycle", (kind: string, value: string) => {
    if (kind === "stop") lifecycle.stopped.push(value);
    else if (kind === "create") lifecycle.created.push(value);
    else if (kind === "revoke") lifecycle.revoked.push(value);
  });
  await page.addInitScript(() => {
    const target = window as unknown as AuditWindow;
    const audit: CameraAudit = {
      requests: [], behavior: "success", resolvePending: () => {}, tracks: [], frames: 0,
      workerStarts: 0, workerStops: 0, storageWrites: 0, databaseCalls: 0, uploads: 0, createdUrls: [], revokedUrls: [],
    };
    target.candidateAudit = audit;
    const announce = (kind: string, value: string) => { void target.candidateLifecycle(kind, value).catch(() => undefined); };
    const makeStream = (): MediaStream => {
      const record = { ended: false }; audit.tracks.push(record);
      const id = String(audit.tracks.length);
      const track = Object.assign(new EventTarget(), {
        kind: "video", enabled: true, muted: false, readyState: "live",
        stop() { if (!record.ended) announce("stop", id); record.ended = true; track.readyState = "ended"; },
        getSettings: () => ({ width: 640, height: 480, facingMode: "environment" }),
      });
      return { getTracks: () => [track], getVideoTracks: () => [track], getAudioTracks: () => [] } as unknown as MediaStream;
    };
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {
      getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream> {
        audit.requests.push(constraints);
        if (constraints.audio !== false) return Promise.reject(new Error("Audio must not be requested."));
        if (audit.behavior === "denied") return Promise.reject(new DOMException("Generated permission refusal", "NotAllowedError"));
        if (audit.behavior === "pending") return new Promise((resolveStream) => { audit.resolvePending = () => resolveStream(makeStream()); });
        return Promise.resolve(makeStream());
      },
    } });
    const streams = new WeakMap<HTMLVideoElement, MediaStream | null>();
    const ready = (video: HTMLVideoElement) => Boolean(streams.get(video));
    const publish = (video: HTMLVideoElement) => {
      if (ready(video)) for (const event of ["loadedmetadata", "loadeddata", "canplay", "playing"]) video.dispatchEvent(new Event(event));
    };
    Object.defineProperty(HTMLVideoElement.prototype, "srcObject", { configurable: true,
      get(this: HTMLVideoElement) { return streams.get(this) ?? null; },
      set(this: HTMLVideoElement, stream: MediaStream | null) { streams.set(this, stream); setTimeout(() => publish(this), 0); },
    });
    for (const property of ["videoWidth", "videoHeight", "readyState"] as const) {
      Object.defineProperty(HTMLVideoElement.prototype, property, { configurable: true,
        get(this: HTMLVideoElement) { return ready(this) ? property === "videoWidth" ? 640 : property === "videoHeight" ? 480 : 4 : 0; },
      });
    }
    HTMLVideoElement.prototype.play = function () { setTimeout(() => publish(this), 0); return Promise.resolve(); };
    HTMLVideoElement.prototype.pause = () => {};
    // eslint-disable-next-line @typescript-eslint/unbound-method -- Reflect.apply preserves the canvas receiver.
    const nativeDraw = CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage = function (...args: unknown[]) {
      if (!(args[0] instanceof HTMLVideoElement)) { Reflect.apply(nativeDraw, this, args); return; }
      if (!ready(args[0])) throw new Error("No generated live frame.");
      const frame = document.createElement("canvas"); frame.width = 640; frame.height = 480;
      const context = frame.getContext("2d");
      if (!context) throw new Error("Generated canvas unavailable.");
      audit.frames++;
      context.fillStyle = "#dce4dc"; context.fillRect(0, 0, 640, 480);
      context.fillStyle = "#fffdf6"; context.beginPath(); context.ellipse(320, 240, 190, 170, 0, 0, Math.PI * 2); context.fill();
      context.fillStyle = "#ba632e"; context.fillRect(245, 175, audit.frames % 2 ? 150 : 63, 115);
      context.strokeStyle = "#96533b"; context.lineWidth = 3;
      for (let x = 250; x < (audit.frames % 2 ? 390 : 305); x += 12) { context.beginPath(); context.moveTo(x, 180); context.lineTo(x + 3, 283); context.stroke(); }
      args[0] = frame;
      try { Reflect.apply(nativeDraw, this, args); } finally { frame.width = 0; frame.height = 0; }
    };
    const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = (blob) => { const url = create(blob); audit.createdUrls.push(url); announce("create", url); return url; };
    URL.revokeObjectURL = (url) => { audit.revokedUrls.push(url); announce("revoke", url); revoke(url); };
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(scriptURL: string | URL, options?: WorkerOptions) { audit.workerStarts++; super(scriptURL, options); }
      override terminate() { audit.workerStops++; super.terminate(); }
    };
    Storage.prototype.setItem = () => { audit.storageWrites++; throw new Error("Persistent input storage is forbidden."); };
    Object.defineProperty(window, "indexedDB", { configurable: true, value: {
      open() { audit.databaseCalls++; throw new Error("Database use is forbidden."); },
    } });
    XMLHttpRequest.prototype.send = () => { audit.uploads++; throw new Error("XHR is unnecessary for this workflow."); };
    Object.defineProperty(navigator, "sendBeacon", { configurable: true, value: () => { audit.uploads++; return false; } });
  });
  return lifecycle;
}

export interface NetworkAudit { forbidden: string[]; assets: string[]; modelHashes: string[]; settle: () => Promise<void> }

/** File metadata only. Requests must resolve to the exact built static inventory. */
async function builtPaths(directory: string, prefix = BASE): Promise<Set<string>> {
  const paths = new Set<string>();
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) throw new Error("Candidate build must not contain symlinks.");
    if (entry.isDirectory()) for (const path of await builtPaths(join(directory, entry.name), `${prefix}${entry.name}/`)) paths.add(path);
    else if (entry.isFile()) paths.add(`${prefix}${entry.name}`);
    else throw new Error("Unexpected candidate build entry.");
  }
  return paths;
}

export async function guardNetwork(context: BrowserContext, origin: string): Promise<NetworkAudit> {
  const staticPaths = await builtPaths(resolve("dist-camera"));
  if (!staticPaths.has(`${BASE}index.html`) || !staticPaths.has(`${BASE}models/plategauge.onnx`)) throw new Error("Build camera candidate before testing.");
  const forbidden: string[] = [], assets: string[] = [], modelHashes: string[] = [];
  const checks: Promise<void>[] = [];
  await context.route("**/*", async (route) => {
    const request = route.request(), url = new URL(request.url());
    if (url.protocol === "blob:" && url.origin === origin) { await route.continue(); return; }
    const documentPath = url.pathname === BASE;
    const queryAllowed = url.search === "" || documentPath && [
      "?capture=1", "?view=evidence", "?benchmark=1", "?unknown=1", "?capture=1&view=evidence", "?capture=1&capture=1",
    ].includes(url.search);
    if (url.origin !== origin || !["http:", "https:"].includes(url.protocol)
      || request.method() !== "GET" || request.postDataBuffer() !== null
      || !(documentPath || staticPaths.has(url.pathname)) || !queryAllowed) {
      forbidden.push(`${request.method()} ${url.href}`); await route.abort("blockedbyclient"); return;
    }
    assets.push(url.pathname); await route.continue();
  });
  context.on("response", (response) => {
    if (new URL(response.url()).pathname !== `${BASE}models/plategauge.onnx` || response.status() !== 200) return;
    const check = response.body().then((body) => {
      expect(body.length).toBe(10_355_122);
      const hash = createHash("sha256").update(body).digest("hex");
      expect(hash).toBe(MODEL_SHA256); modelHashes.push(hash);
    });
    void check.catch(() => undefined); checks.push(check);
  });
  return { forbidden, assets, modelHashes, settle: async () => { await Promise.all(checks); } };
}

export async function setup(page: Page, context: BrowserContext, baseURL: string | undefined, route = "?capture=1") {
  if (!baseURL || new URL(baseURL).hostname !== "127.0.0.1") throw new Error("Explicit loopback candidate URL required.");
  const network = await guardNetwork(context, new URL(baseURL).origin);
  const lifecycle = await installCamera(page);
  await page.goto(`${BASE}${route}`);
  return { network, lifecycle };
}

export async function takeBefore(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Open camera", exact: true }).click();
  const capture = page.getByRole("button", { name: "Take before photo", exact: true });
  await expect(capture).toBeEnabled(); await capture.click();
  await expect(page.getByRole("img", { name: "Your before photo", exact: true })).toBeVisible();
}

export async function takePair(page: Page): Promise<void> {
  await takeBefore(page);
  await page.getByRole("button", { name: "Continue to after", exact: true }).click();
  await page.getByRole("button", { name: "Open camera", exact: true }).click();
  const capture = page.getByRole("button", { name: "Take after photo", exact: true });
  await expect(capture).toBeEnabled(); await capture.click();
  await page.getByRole("button", { name: "Review & estimate", exact: true }).click();
}

export async function expectPrivate(page: Page, network: NetworkAudit): Promise<void> {
  await network.settle(); expect(network.forbidden).toEqual([]);
  const state = await page.evaluate(() => {
    const audit = (window as unknown as AuditWindow).candidateAudit;
    return { storage: audit.storageWrites, databases: audit.databaseCalls, uploads: audit.uploads,
      local: localStorage.length, session: sessionStorage.length, live: audit.tracks.filter((track) => !track.ended).length };
  });
  expect(state).toEqual({ storage: 0, databases: 0, uploads: 0, local: 0, session: 0, live: 0 });
  expect(await page.context().cookies()).toEqual([]);
}

export async function expectInert(page: Page, network: NetworkAudit): Promise<void> {
  expect(await page.evaluate(() => {
    const audit = (window as unknown as AuditWindow).candidateAudit;
    return { camera: audit.requests.length, workers: audit.workerStarts };
  })).toEqual({ camera: 0, workers: 0 });
  await expect(page.getByTestId("experimental-estimate-result")).toHaveCount(0);
  expect(network.assets.filter((path) => /\/models\/|\/ort\//.test(path))).toEqual([]);
  await expectPrivate(page, network);
}

export interface SessionFile { name: string; mimeType: string; buffer: Buffer }
export async function saveSession(page: Page, keyboard = false): Promise<SessionFile> {
  const button = page.getByRole("button", { name: "Save session", exact: true });
  await expect(button).toBeEnabled();
  const saving = page.waitForEvent("download");
  if (keyboard) { await button.focus(); await expect(button).toBeFocused(); await page.keyboard.press("Enter"); } else await button.click();
  const download = await saving;
  expect(await download.failure()).toBeNull(); expect(download.suggestedFilename()).toMatch(/\.plategauge\.json$/);
  const path = await download.path();
  if (!path) throw new Error("Generated session download unavailable.");
  // A download event can precede React's completion/focus effect. Wait for the
  // user-visible finished state before a subsequent keyboard action can race it.
  await expect(page.locator(".rc-session-status")).toContainText("Download requested.");
  await expect(button).toBeEnabled(); await expect(button).toBeFocused();
  return { name: download.suggestedFilename(), mimeType: "application/json", buffer: await readFile(path) };
}

export async function resumeSession(page: Page, file: SessionFile, keyboard = false): Promise<void> {
  const button = page.getByRole("button", { name: "Resume session", exact: true });
  await expect(button).toBeEnabled();
  const choosing = page.waitForEvent("filechooser");
  if (keyboard) { await button.focus(); await expect(button).toBeFocused(); await page.keyboard.press("Enter"); } else await button.click();
  await (await choosing).setFiles(file);
}

export async function cropHashes(page: Page): Promise<string[]> {
  const toggle = page.getByRole("button", { name: "Model input", exact: true });
  if (await toggle.getAttribute("aria-pressed") !== "true") await toggle.click();
  const canvases = page.getByTestId("model-crop-preview");
  await expect(canvases).toHaveCount(2);
  return canvases.evaluateAll(async (nodes) => Promise.all(nodes.map(async (node) => {
    const canvas = node as HTMLCanvasElement;
    if (canvas.width !== 224 || canvas.height !== 224) throw new Error("Wrong model-crop dimensions.");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Generated crop review unavailable.");
    const pixels = context.getImageData(0, 0, 224, 224).data;
    const digest = await crypto.subtle.digest("SHA-256", new Uint8Array(pixels)); pixels.fill(0);
    return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
  })));
}
