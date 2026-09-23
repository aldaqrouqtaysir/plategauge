// @vitest-environment node
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { afterEach, describe, expect, it } from "vitest";

const helper = pathToFileURL(resolve("scripts/media-output.mjs")).href;
const roots: string[] = [];
async function fixture() {
  const root = await mkdtemp(join(await realpath(tmpdir()), "plategauge-media-test-"));
  roots.push(root);
  const repository = join(root, "repository");
  await mkdir(join(repository, "reports/media"), { recursive: true });
  const historical = join(repository, "reports/media/historical.png");
  await writeFile(historical, "synthetic preserved evidence");
  return { root, repository, historical };
}
function run(target: string | undefined, repository: string) {
  return spawnSync(process.execPath, ["--input-type=module", "-e",
    `const m=await import(${JSON.stringify(helper)}); await m.reserveMediaOutput(${JSON.stringify(target) ?? "undefined"},${JSON.stringify(repository)});`,
  ], { encoding: "utf8", timeout: 10_000, windowsHide: true });
}
afterEach(async () => {
  const temporary = await realpath(tmpdir());
  for (const root of roots.splice(0)) {
    const canonical = await realpath(root);
    if (!basename(canonical).startsWith("plategauge-media-test-") || relative(temporary, canonical) !== basename(canonical)) {
      throw new Error("Refuse an unexpected synthetic cleanup root");
    }
    await rm(canonical, { recursive: true, force: true });
  }
});
describe("media output preserves historical evidence", () => {
  it("reserves only a fresh external output and rejects its reuse without changing bytes", async () => {
    const item = await fixture(), output = join(item.root, "fresh");
    expect(run(output, item.repository).status).toBe(0);
    await writeFile(join(output, "existing.webm"), "synthetic recording");
    expect(run(output, item.repository).status).not.toBe(0);
    expect(await readFile(join(output, "existing.webm"), "utf8")).toBe("synthetic recording");
    expect(await readFile(item.historical, "utf8")).toBe("synthetic preserved evidence");
  });
  it("rejects omitted, relative, in-checkout and checkout-ancestor output", async () => {
    const item = await fixture();
    for (const output of [undefined, "relative-output", item.repository, join(item.repository, "new"), item.root]) {
      expect(run(output, item.repository).status).not.toBe(0);
    }
    expect(await readFile(item.historical, "utf8")).toBe("synthetic preserved evidence");
  });
  it("rejects existing files and missing parents without creating them", async () => {
    const item = await fixture();
    expect(run(item.historical, item.repository).status).not.toBe(0);
    expect(run(join(item.root, "missing-parent/output"), item.repository).status).not.toBe(0);
    await expect(readFile(join(item.root, "missing-parent"))).rejects.toMatchObject({ code: "ENOENT" });
  });
  it("rejects linked output and linked ancestry", async () => {
    const item = await fixture(), destination = join(item.root, "destination"), link = join(item.root, "linked");
    await mkdir(destination);
    await symlink(destination, link, "junction");
    expect(run(link, item.repository).status).not.toBe(0);
    expect(run(join(link, "new"), item.repository).status).not.toBe(0);
    await expect(readFile(join(destination, "new"))).rejects.toMatchObject({ code: "ENOENT" });
  });
  it("generates the actual timestamp rather than a frozen historical date", () => {
    const result = spawnSync(process.execPath, ["--input-type=module", "-e",
      `const m=await import(${JSON.stringify(helper)}); console.log(m.mediaTimestamp(new Date('2030-02-03T04:05:06Z'))); console.log(m.mediaTimestamp());`,
    ], { encoding: "utf8", timeout: 10_000, windowsHide: true });
    expect(result.status, result.stderr).toBe(0);
    const lines = result.stdout.trim().split(/\r?\n/);
    expect(lines[0]).toBe("2030-02-03T04:05:06.000Z");
    expect(Math.abs(Date.now() - Date.parse(lines[1]!))).toBeLessThan(10_000);
  });
  it.each(["capture-portfolio-assets.mjs", "record-local-demo.mjs"])("%s rejects missing output before launching a browser", (script) => {
    const result = spawnSync(process.execPath, [resolve("scripts", script)], { encoding: "utf8", timeout: 10_000, windowsHide: true });
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("--output requires a new absolute directory");
  });
});
