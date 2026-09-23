import { lstat, mkdir, realpath } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";

function contains(parent, child) {
  const path = relative(parent, child);
  return path === "" || (!isAbsolute(path) && path !== ".." && !path.startsWith(`..${sep}`));
}

/** Reserve a fresh external directory; never reuse or erase historical media. */
export async function reserveMediaOutput(raw, repository) {
  if (typeof raw !== "string" || !isAbsolute(raw)) {
    throw new Error("--output requires a new absolute directory outside the checkout.");
  }
  const target = resolve(raw), root = await realpath(repository);
  if (contains(root, target) || contains(target, root)) {
    throw new Error("Media output must be separate from the checkout and its ancestors.");
  }
  for (let ancestor = dirname(target); ; ancestor = dirname(ancestor)) {
    const info = await lstat(ancestor);
    if (info.isSymbolicLink() || !info.isDirectory()) {
      throw new Error("Media output requires existing ordinary directory ancestry.");
    }
    if (dirname(ancestor) === ancestor) break;
  }
  // mkdir without recursive or force is exclusive, including for a dangling link.
  await mkdir(target);
  return target;
}

export function mediaTimestamp(now = new Date()) {
  return now.toISOString();
}
