/** Local capture/experimental inference approval does not authorize publication. */
export function localCaptureMode(development: boolean, hostname: string, search: string): "camera" | "fixtures" | null {
  if (!development || !["localhost", "127.0.0.1", "[::1]", "::1"].includes(hostname)) return null;
  const params = new URLSearchParams(search);
  if (["capture", "capturePrototype", "captureFixtures"].some((key) => params.getAll(key).length > 1)) return null;
  const camera = params.get("capture") === "1" || params.get("capturePrototype") === "1";
  const fixtures = params.get("captureFixtures") === "1";
  if (camera && fixtures) return null;
  return camera ? "camera" : fixtures ? "fixtures" : null;
}

/** Unknown/ambiguous selectors retain the benchmark, never start a capture. */
export function localPreviewView(development: boolean, hostname: string, search: string): "home" | "evidence" | "camera" | "fixtures" | null {
  if (localCaptureMode(development, hostname, "?capture=1") !== "camera") return null;
  const params = new URLSearchParams(search);
  if (params.size === 0) return "home";
  if (params.size !== 1) return null;
  if (params.get("view") === "evidence" || params.get("benchmark") === "1") return "evidence";
  return localCaptureMode(development, hostname, search);
}
