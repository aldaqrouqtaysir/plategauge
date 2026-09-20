import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(projectRoot, "..");
const sourceDirectory = resolve(projectRoot, "node_modules", "onnxruntime-web", "dist");
const targetDirectory = resolve(projectRoot, "public", "ort");
const legalDirectory = resolve(projectRoot, "public", "legal");

function assertReplaceableDirectory(directory, expectedRelativeTarget, label) {
  const relativeTarget = relative(projectRoot, directory);
  if (
    relativeTarget !== expectedRelativeTarget ||
    relativeTarget.startsWith(`..${process.platform === "win32" ? "\\" : "/"}`) ||
    isAbsolute(relativeTarget)
  ) {
    throw new Error(`Refusing to replace unexpected ${label} directory: ${directory}`);
  }
}

assertReplaceableDirectory(targetDirectory, join("public", "ort"), "ONNX Runtime");
assertReplaceableDirectory(legalDirectory, join("public", "legal"), "legal notice");

await rm(targetDirectory, { recursive: true, force: true });
await mkdir(targetDirectory, { recursive: true });
const runtimeFiles = ["ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"];

await Promise.all(
  runtimeFiles.map((file) => cp(join(sourceDirectory, file), join(targetDirectory, file))),
);

await rm(legalDirectory, { recursive: true, force: true });
await mkdir(legalDirectory, { recursive: true });
await Promise.all([
  cp(join(repositoryRoot, "LICENSE"), join(legalDirectory, "LICENSE.txt")),
  cp(join(repositoryRoot, "NOTICE"), join(legalDirectory, "NOTICE.txt")),
  cp(
    join(repositoryRoot, "reports", "security", "node-production-licenses.json"),
    join(legalDirectory, "THIRD_PARTY_LICENSES.json"),
  ),
  cp(
    join(repositoryRoot, "docs", "PRIVACY_NOTICE.md"),
    join(legalDirectory, "PRIVACY_NOTICE.md"),
  ),
  cp(
    join(repositoryRoot, "docs", "AI_ASSISTANCE_PUBLIC.md"),
    join(legalDirectory, "AI_ASSISTANCE_LOG.md"),
  ),
]);
