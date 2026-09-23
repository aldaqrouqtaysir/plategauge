import { EXPERIMENTAL_MODEL } from "./contract";

/** Read at most the pinned artifact size; never buffer an unbounded response body. */
export async function readModelBytes(response: Response, expectedUrl: URL): Promise<ArrayBuffer> {
  if (!response.ok || response.status !== 200 || response.redirected
    || response.url !== expectedUrl.href || !["basic", "default"].includes(response.type)) {
    await response.body?.cancel().catch(() => undefined);
    throw new Error("model response rejected");
  }
  const mime = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  const length = response.headers.get("content-length");
  // Some static servers omit ONNX's MIME type. URL/size checks still apply here;
  // the caller must verify the pinned SHA-256 before initializing the runtime.
  if ((mime && !["application/octet-stream", "application/onnx", "application/x-onnx"].includes(mime))
    || (length !== null && (!/^\d+$/.test(length) || !Number.isSafeInteger(Number(length))
      || Number(length) > EXPERIMENTAL_MODEL.bytes))) {
    await response.body?.cancel().catch(() => undefined);
    throw new Error("model headers rejected");
  }
  if (!response.body) throw new Error("model body missing");
  const reader = response.body.getReader();
  const bytes = new Uint8Array(EXPERIMENTAL_MODEL.bytes);
  let offset = 0;
  let complete = false;
  try {
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      if (!(chunk.value instanceof Uint8Array) || chunk.value.byteLength > bytes.length - offset) {
        throw new Error("model body exceeds bound");
      }
      bytes.set(chunk.value, offset);
      offset += chunk.value.byteLength;
    }
    if (offset !== bytes.length) throw new Error("model size mismatch");
    complete = true;
    return bytes.buffer;
  } finally {
    if (!complete) {
      bytes.fill(0);
      await reader.cancel().catch(() => undefined);
    }
    reader.releaseLock();
  }
}
