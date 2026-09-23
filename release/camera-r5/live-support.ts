import { createHash, randomUUID } from "node:crypto";
import { existsSync, lstatSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { get as getHttp } from "node:http";
import { get as getHttps } from "node:https";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { expect, type BrowserContext, type Page } from "../../web/node_modules/@playwright/test/index.js";
import {
  BASE, MODEL_SHA256, MODEL_VERSION, installCamera, takePair,
  type AuditWindow, type Lifecycle, type NetworkAudit,
} from "../../web/tests/camera-candidate/support";

export { BASE, MODEL_SHA256, MODEL_VERSION };
export const SOURCE_COMMIT = "40493849af148124a45b6a6c65d9c9146c03fdb4";
export const INVENTORY_SHA256 = "4f187ffba720de77cc2349d1fcdbd2b29d03c131aac132006b036fc8514e57e5";
export const SOURCE_URL = "https://github.com/aldaqrouqtaysir/plategauge/tree/" + SOURCE_COMMIT;
const PUBLIC_URL = "https://aldaqrouqtaysir.github.io/plategauge/";
const LOCAL_URL = "http://127.0.0.1:4199/plategauge/";
const MAX_FILE_BYTES = 32 * 1024 * 1024;
const MAX_TOTAL_BYTES = 64 * 1024 * 1024;
const REQUIRED = [
  "index.html", "models/plategauge.onnx", "models/release.json",
  "ort/ort-wasm-simd-threaded.mjs", "ort/ort-wasm-simd-threaded.wasm",
  "evidence/benchmark-evidence.json", "legal/CAMERA_PRIVACY_NOTICE.md",
  "legal/CAMERA_SYSTEM_CARD.md", "legal/PILLOW_RESAMPLING_NOTICE.md",
  "legal/LICENSE.txt", "legal/NOTICE.txt", "legal/THIRD_PARTY_LICENSES.json",
];
export interface Asset { path: string; size: number; sha256: string }
export interface Inventory { schemaVersion: 1; appSourceCommit: typeof SOURCE_COMMIT; files: Asset[] }
function record(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)
    || Object.keys(value).sort().join(",") !== keys.sort().join(",")) throw new Error("Invalid approved inventory schema.");
  return value as Record<string, unknown>;
}
export function parseInventory(value: unknown): Inventory {
  const top = record(value, ["schemaVersion", "appSourceCommit", "files"]);
  if (top.schemaVersion !== 1 || top.appSourceCommit !== SOURCE_COMMIT
    || !Array.isArray(top.files) || top.files.length !== 45) throw new Error("Inventory is not the approved r5 camera artifact.");
  const seen = new Set<string>();
  let total = 0, previous = "";
  const files = top.files.map((item): Asset => {
    const file = record(item, ["path", "size", "sha256"]);
    if (typeof file.path !== "string" || file.path.length > 200
      || !/^[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*$/.test(file.path)
      || file.path.split("/").some((part) => part === "." || part === "..")
      || !/^(?:index\.html|(?:assets|evidence|examples|legal|models|ort)\/[^/]+)$/.test(file.path)
      || /\.(?:map|base64|py|ts|tsx)$/i.test(file.path)
      || file.path.toLowerCase() === "legal/ai_assistance_log.md"
      || seen.has(file.path.toLowerCase()) || file.path <= previous
      || typeof file.size !== "number" || !Number.isSafeInteger(file.size)
      || file.size <= 0 || file.size > MAX_FILE_BYTES
      || typeof file.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(file.sha256)) {
      throw new Error("Invalid, unsorted or unsafe approved inventory entry.");
    }
    seen.add(file.path.toLowerCase()); total += file.size; previous = file.path;
    return { path: file.path, size: file.size, sha256: file.sha256 };
  });
  if (total > MAX_TOTAL_BYTES || REQUIRED.some((path) => !files.some((file) => file.path === path))) {
    throw new Error("Approved inventory is incomplete or exceeds the smoke budget.");
  }
  const model = files.find((file) => file.path === "models/plategauge.onnx")!;
  const evidence = files.find((file) => file.path === "evidence/benchmark-evidence.json")!;
  if (model.size !== 10_355_122 || model.sha256 !== MODEL_SHA256
    || evidence.size !== 22_142 || evidence.sha256 !== "c6f7d435d077bc67649d192efb169e247a1a208e5e9bdc0b6feabd772887c412") {
    throw new Error("Frozen model or evidence identity differs from the approved candidate.");
  }
  return { schemaVersion: 1, appSourceCommit: SOURCE_COMMIT, files };
}

/** One negative read outside the asset proxy: fixed path, no redirects or body buffering. */
export async function expectRetiredResourceUnavailable(): Promise<void> {
  const { baseURL } = smokeConfiguration();
  const target = new URL("legal/AI_ASSISTANCE_LOG.md", baseURL);
  const get = target.protocol === "https:" ? getHttps : getHttp;
  await new Promise<void>((resolveRequest, reject) => {
    const request = get(target, { headers: { "Accept": "text/plain", "Accept-Encoding": "identity" } }, (response) => {
      const status = response.statusCode;
      // The status is the entire observation; never consume an arbitrary error body.
      response.destroy();
      if (status === 404) resolveRequest();
      else reject(new Error(`Retired resource must return 404 without redirects; received ${status}.`));
    });
    request.setTimeout(10_000, () => request.destroy(new Error("Retired-resource check timed out.")));
    request.on("error", reject);
  });
}
export function smokeConfiguration(): { mode: "https" | "local"; baseURL: string; inventory: Inventory } {
  const mode = process.env.PLATEGAUGE_CAMERA_SMOKE_MODE;
  if (mode !== "https" && mode !== "local") throw new Error("Smoke mode must be explicitly https or local.");
  const inventoryPath = process.env.PLATEGAUGE_CAMERA_SMOKE_INVENTORY;
  if (!inventoryPath || !isAbsolute(inventoryPath)) throw new Error("An absolute approved inventory JSON path is required.");
  const stat = lstatSync(inventoryPath);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size < 1 || stat.size > 128 * 1024) {
    throw new Error("Approved inventory must be a bounded regular JSON file.");
  }
  const bytes = readFileSync(inventoryPath);
  if (createHash("sha256").update(bytes).digest("hex") !== INVENTORY_SHA256) {
    throw new Error("Inventory bytes do not match the separately approved camera inventory.");
  }
  const inventory = parseInventory(JSON.parse(bytes.toString("utf8")) as unknown);
  return { mode, baseURL: mode === "local" ? LOCAL_URL : PUBLIC_URL, inventory };
}

/** Reserve a new diagnostics tree; worker config reloads inherit this run's nonce. */
export function reserveDiagnosticsDirectory(raw: string | undefined, repository: string): string {
  if (!raw || !isAbsolute(raw)) throw new Error("An absolute fresh diagnostics directory is required.");
  const target = resolve(raw), repo = resolve(repository), inside = relative(repo, target);
  if (!inside || (!isAbsolute(inside) && inside !== ".." && !inside.startsWith(".." + sep))) {
    throw new Error("Diagnostics must be outside the checkout.");
  }
  // A parent of the checkout is also not a diagnostics target.
  const contains = relative(target, repo);
  if (!contains || (!isAbsolute(contains) && contains !== ".." && !contains.startsWith(".." + sep))) {
    throw new Error("Diagnostics must not contain the checkout.");
  }
  for (let ancestor = target; ; ancestor = dirname(ancestor)) {
    if (existsSync(ancestor) && (lstatSync(ancestor).isSymbolicLink() || !lstatSync(ancestor).isDirectory())) {
      throw new Error("Diagnostics ancestry must contain ordinary directories only.");
    }
    if (dirname(ancestor) === ancestor) break;
  }
  const marker = join(target, ".camera-smoke-owner.json");
  const inherited = process.env.PLATEGAUGE_CAMERA_SMOKE_INTERNAL_OUTPUT_NONCE;
  if (inherited) {
    if (!/^[a-f0-9-]{36}$/.test(inherited) || !existsSync(marker) || lstatSync(marker).isSymbolicLink()
      || !lstatSync(marker).isFile() || lstatSync(marker).size > 4096) throw new Error("Invalid diagnostics ownership marker.");
    const saved = record(JSON.parse(readFileSync(marker, "utf8")) as unknown, ["nonce", "path", "source"]);
    if (saved.nonce !== inherited || saved.path !== target || saved.source !== SOURCE_COMMIT) {
      throw new Error("Diagnostics belong to another invocation.");
    }
  } else {
    if (existsSync(target)) throw new Error("Diagnostics already exist; select a new path to retain previous evidence.");
    mkdirSync(dirname(target), { recursive: true });
    mkdirSync(target);
    const nonce = randomUUID();
    writeFileSync(marker, JSON.stringify({ nonce, path: target, source: SOURCE_COMMIT }), { flag: "wx" });
    process.env.PLATEGAUGE_CAMERA_SMOKE_INTERNAL_OUTPUT_NONCE = nonce;
  }
  return target;
}
export function assetForUrl(raw: string, baseURL: string, inventory: Inventory): Asset | undefined {
  const base = new URL(baseURL), url = new URL(raw);
  if (![PUBLIC_URL, LOCAL_URL].includes(baseURL) || url.origin !== base.origin
    || url.protocol !== base.protocol || url.username || url.password || url.hash) return undefined;
  const document = url.pathname === BASE;
  if (url.search && (!document || ![
    "?capture=1", "?view=evidence", "?unknown=1", "?capture=1&view=evidence",
  ].includes(url.search))) return undefined;
  const path = document ? "index.html" : url.pathname.startsWith(BASE) ? url.pathname.slice(BASE.length) : "";
  return inventory.files.find((asset) => asset.path === path);
}
export interface LiveNetwork extends NetworkAudit { verified: Set<string> }

/** Actual allowlisted GET responses are verified before browser execution. */
export async function guardLiveNetwork(context: BrowserContext, baseURL: string, inventory: Inventory): Promise<LiveNetwork> {
  const forbidden: string[] = [], assets: string[] = [], modelHashes: string[] = [];
  const verified = new Set<string>(), checks = new Set<Promise<void>>();
  await context.routeWebSocket("**/*", (socket) => {
    forbidden.push("WebSocket refused"); socket.close();
  });
  await context.route("**/*", async (route) => {
    const request = route.request(), asset = assetForUrl(request.url(), baseURL, inventory);
    const requestHeaders = await request.allHeaders();
    if (!asset || request.method() !== "GET" || request.postDataBuffer() !== null || request.redirectedFrom()
      || requestHeaders.authorization || requestHeaders.cookie || requestHeaders["proxy-authorization"]) {
      forbidden.push("Rejected request: " + request.method() + " " + new URL(request.url()).pathname);
      await route.abort("blockedbyclient"); return;
    }
    const pending = (async () => {
      const response = await route.fetch({ maxRedirects: 0, maxRetries: 0, timeout: 30_000 });
      try {
        if (response.status() !== 200 || response.url() !== request.url() || response.headers().location
          || response.headers()["set-cookie"]) {
          throw new Error("Non-200, changed URL, redirect or cookie-setting response.");
        }
        const length = response.headers()["content-length"];
        if (length && (!/^\d+$/.test(length) || Number(length) > MAX_FILE_BYTES)) throw new Error("Response exceeds smoke budget.");
        const body = await response.body();
        if (body.length !== asset.size || createHash("sha256").update(body).digest("hex") !== asset.sha256) {
          throw new Error("Response differs from the approved inventory.");
        }
        assets.push(new URL(request.url()).pathname); verified.add(asset.path);
        if (asset.path === "models/plategauge.onnx") modelHashes.push(asset.sha256);
        // APIResponse is decoded. Preserve application/security/MIME headers;
        // omit transport headers to avoid applying compression twice.
        const headers = { ...response.headers() };
        delete headers["content-encoding"]; delete headers["content-length"]; delete headers["transfer-encoding"];
        await route.fulfill({ status: 200, headers, body });
      } finally { await response.dispose(); }
    })();
    checks.add(pending);
    try { await pending; }
    catch { forbidden.push("Rejected response: " + asset.path); await route.abort("failed").catch(() => undefined); }
    finally { checks.delete(pending); }
  });
  return {
    forbidden, assets, modelHashes, verified,
    settle: async () => {
      while (checks.size) await Promise.allSettled([...checks]);
      expect(forbidden).toEqual([]);
    },
  };
}
type SentinelWindow = AuditWindow & {
  cameraSmokeSentinel?: { media: MediaDevices; generated: MediaDevices["getUserMedia"] };
};
/** No native getUserMedia invocation is used as a probe. Re-arm after navigation. */
export async function armGeneratedCamera(page: Page): Promise<void> {
  await page.evaluate(() => {
    const target = window as unknown as SentinelWindow;
    const own = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
    const media = navigator.mediaDevices, generated = media?.getUserMedia;
    if (!target.candidateAudit || own?.value !== media
      || Object.keys(media).join(",") !== "getUserMedia"
      || typeof generated !== "function"
      || !Function.prototype.toString.call(generated).includes("audit.requests.push")
      || Function.prototype.toString.call(generated).includes("[native code]")) {
      throw new Error("Generated camera installation could not be proven; refusing camera actions.");
    }
    Object.defineProperty(target, "cameraSmokeSentinel", {
      value: { media, generated }, configurable: false, writable: false,
    });
    Object.defineProperty(media, "getUserMedia", { value: generated, configurable: false, writable: false });
  });
  await requireGeneratedCamera(page);
}
export async function requireGeneratedCamera(page: Page): Promise<void> {
  expect(await page.evaluate(() => {
    const target = window as unknown as SentinelWindow, saved = target.cameraSmokeSentinel;
    return Boolean(saved && navigator.mediaDevices === saved.media && navigator.mediaDevices.getUserMedia === saved.generated);
  })).toBe(true);
}
export async function setupLive(page: Page, context: BrowserContext, route = ""):
Promise<{ network: LiveNetwork; lifecycle: Lifecycle }> {
  const { baseURL, inventory } = smokeConfiguration();
  const network = await guardLiveNetwork(context, baseURL, inventory);
  const lifecycle = await installCamera(page);
  await page.goto(baseURL + route, { waitUntil: "domcontentloaded" });
  await armGeneratedCamera(page);
  await expect(page.locator("html")).toHaveCSS("scroll-behavior", "auto");
  return { network, lifecycle };
}
export async function generatedPair(page: Page): Promise<void> {
  await requireGeneratedCamera(page);
  await takePair(page);
  await requireGeneratedCamera(page);
  expect(await page.evaluate(() => (window as unknown as AuditWindow).candidateAudit.requests.length)).toBe(2);
}
