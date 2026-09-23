import { lstat, mkdir, mkdtemp, readFile, readdir, realpath, rename, rmdir, unlink, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(projectRoot, "..");
const publicDirectory = join(projectRoot, "public");
const lockDirectory = join(publicDirectory, ".plategauge-assets.lock");
const sourceDirectory = join(projectRoot, "node_modules", "onnxruntime-web", "dist");
const groups = [
  {
    name: "ort",
    sources: [
      [join(sourceDirectory, "ort-wasm-simd-threaded.mjs"), "ort-wasm-simd-threaded.mjs"],
      [join(sourceDirectory, "ort-wasm-simd-threaded.wasm"), "ort-wasm-simd-threaded.wasm"],
    ],
  },
  {
    name: "legal",
    sources: [
      [join(repositoryRoot, "LICENSE"), "LICENSE.txt"],
      [join(repositoryRoot, "NOTICE"), "NOTICE.txt"],
      [join(repositoryRoot, "reports", "security", "node-production-licenses.json"), "THIRD_PARTY_LICENSES.json"],
      [join(repositoryRoot, "docs", "PRIVACY_NOTICE.md"), "PRIVACY_NOTICE.md"],
      [join(repositoryRoot, "docs", "AI_ASSISTANCE_PUBLIC.md"), "AI_ASSISTANCE_LOG.md"],
    ],
  },
];

async function optionalStat(path) {
  try {
    return await lstat(path);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function isWithin(parent, path) {
  const pathFromParent = relative(parent, path);
  return pathFromParent !== ".." && !pathFromParent.startsWith(`..${process.platform === "win32" ? "\\" : "/"}`)
    && !isAbsolute(pathFromParent);
}

async function assertPlainDirectory(path, mayBeMissing = false) {
  const info = await optionalStat(path);
  if (!info && mayBeMissing) return false;
  if (!info?.isDirectory() || info.isSymbolicLink()) {
    throw new Error(`Refusing non-directory or linked asset path: ${path}`);
  }
  // Comparing the full real path also rejects links/junctions in ancestors.
  if (relative(resolve(path), await realpath(path)) !== "") {
    throw new Error(`Refusing redirected asset directory: ${path}`);
  }
  return true;
}

async function assertManagedDirectory(path, names) {
  if (!await assertPlainDirectory(path, true)) return false;
  const entries = await readdir(path, { withFileTypes: true });
  for (const entry of entries) {
    if (!names.includes(entry.name) || !entry.isFile() || entry.isSymbolicLink()) {
      throw new Error(`Refusing unexplained or linked file in managed assets: ${join(path, entry.name)}`);
    }
  }
  return true;
}

async function preflightSources() {
  await assertPlainDirectory(repositoryRoot);
  await assertPlainDirectory(projectRoot);
  if (await assertPlainDirectory(publicDirectory, true)) {
    for (const group of groups) {
      await assertManagedDirectory(join(publicDirectory, group.name), group.sources.map(([, name]) => name));
    }
  }
  return Promise.all(groups.map(async (group) => ({
    ...group,
    files: await Promise.all(group.sources.map(async ([source, name]) => {
      const info = await lstat(source);
      // pnpm's package-directory links are allowed only when their resolved files stay in
      // this repository. Direct source-file links are not part of the asset contract.
      if (!info.isFile() || info.isSymbolicLink() || !isWithin(repositoryRoot, await realpath(source))) {
        throw new Error(`Refusing linked, non-file, or external asset source: ${source}`);
      }
      return { name, bytes: await readFile(source) };
    })),
    backedUp: false,
    promoted: false,
  })));
}

async function removeManagedDirectory(path, names) {
  if (!await assertManagedDirectory(path, names)) return;
  // Never recursively remove a path. Only regular, allowlisted generated files are unlinked.
  for (const entry of await readdir(path)) await unlink(join(path, entry));
  await rmdir(path);
}

function combinedError(original, additional, message) {
  return original ? new AggregateError([original, additional], message) : additional;
}

// Missing inputs leave the last generated assets untouched, before even creating a lock.
const preparedGroups = await preflightSources();
if (!await assertPlainDirectory(publicDirectory, true)) await mkdir(publicDirectory);
await assertPlainDirectory(publicDirectory);
try {
  await mkdir(lockDirectory);
} catch (error) {
  if (error.code === "EEXIST") {
    throw new Error("Asset preparation is already running or an interrupted lock remains; inspect public/.plategauge-assets.lock before retrying.");
  }
  throw error;
}

let stagingDirectory;
let failure;
let mayCleanStaging = true;
try {
  await assertPlainDirectory(publicDirectory);
  stagingDirectory = await mkdtemp(join(publicDirectory, ".plategauge-assets-stage-"));
  for (const group of preparedGroups) {
    const staged = join(stagingDirectory, group.name);
    await mkdir(staged);
    for (const file of group.files) await writeFile(join(staged, file.name), file.bytes, { flag: "wx" });
  }
  // Validate every destination again under the exclusive preparation lock before promotion.
  for (const group of preparedGroups) {
    await assertManagedDirectory(join(publicDirectory, group.name), group.files.map((file) => file.name));
  }
  for (const group of preparedGroups) {
    await assertPlainDirectory(publicDirectory);
    await assertPlainDirectory(stagingDirectory);
    const target = join(publicDirectory, group.name);
    if (await assertManagedDirectory(target, group.files.map((file) => file.name))) {
      await rename(target, join(stagingDirectory, `${group.name}-previous`));
      group.backedUp = true;
    }
    await rename(join(stagingDirectory, group.name), target);
    group.promoted = true;
  }
} catch (error) {
  failure = error;
  // Keep the old assets until both directories have been promoted. Restore them on failure.
  try {
    for (const group of [...preparedGroups].reverse()) {
      if (!group.promoted && !group.backedUp) continue;
      await assertPlainDirectory(publicDirectory);
      await assertPlainDirectory(stagingDirectory);
      const target = join(publicDirectory, group.name);
      if (group.promoted) {
        await assertManagedDirectory(target, group.files.map((file) => file.name));
        await rename(target, join(stagingDirectory, group.name));
      }
      if (group.backedUp) await rename(join(stagingDirectory, `${group.name}-previous`), target);
    }
  } catch (rollbackError) {
    mayCleanStaging = false;
    failure = combinedError(failure, rollbackError, `Asset promotion and rollback failed; recover preserved files in ${stagingDirectory}`);
  }
} finally {
  try {
    if (stagingDirectory && mayCleanStaging) {
      await assertPlainDirectory(publicDirectory);
      await assertPlainDirectory(stagingDirectory);
      const allowed = preparedGroups.flatMap((group) => [group.name, `${group.name}-previous`]);
      if ((await readdir(stagingDirectory)).some((name) => !allowed.includes(name))) {
        throw new Error(`Unexpected staging content preserved for inspection: ${stagingDirectory}`);
      }
      for (const group of preparedGroups) {
        const names = group.files.map((file) => file.name);
        await removeManagedDirectory(join(stagingDirectory, group.name), names);
        await removeManagedDirectory(join(stagingDirectory, `${group.name}-previous`), names);
      }
      await rmdir(stagingDirectory);
    }
  } catch (cleanupError) {
    failure = combinedError(failure, cleanupError, "Asset preparation failed; cleanup details are preserved alongside the original failure.");
  }
  try {
    await assertPlainDirectory(publicDirectory);
    await assertPlainDirectory(lockDirectory);
    await rmdir(lockDirectory);
  } catch (lockError) {
    failure = combinedError(failure, lockError, "Asset preparation failed; the preparation lock requires inspection.");
  }
}
if (failure) throw failure;
