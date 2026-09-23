export type CameraView = "home" | "camera" | "evidence";

export const CANDIDATE_ID = "camera-experimental-r1";
const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

/** A build-time capability, never enabled by a query parameter or local storage. */
export function candidateContextAllowed(
  enabled: boolean,
  hostname: string,
  protocol: string,
  secureContext: boolean,
  topLevel: boolean,
): boolean {
  if (!enabled || !secureContext || !topLevel) return false;
  if (LOOPBACK.has(hostname)) return protocol === "http:" || protocol === "https:";
  return protocol === "https:" && hostname === "aldaqrouqtaysir.github.io";
}

/** Ambiguous or unsupported URLs show a safe landing view, never camera activation. */
export function candidateView(search: string): CameraView {
  const params = new URLSearchParams(search);
  if (params.size !== 1) return "home";
  if (params.get("capture") === "1") return "camera";
  if (params.get("view") === "evidence") return "evidence";
  return "home";
}
