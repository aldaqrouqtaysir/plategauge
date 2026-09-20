import assert from "node:assert/strict";
import test from "node:test";

import { parseArguments } from "./collect-browser-observation.mjs";

const minimumArguments = [
  "--web-root",
  "dist",
  "--base-path",
  "/plategauge/",
  "--warmups",
  "3",
  "--measurements",
  "20",
  "--browser-channel",
  "chrome",
];

test("fixed harness arguments require no caller-supplied image paths", () => {
  const options = parseArguments(minimumArguments);

  assert.equal(options.headless, false);
  assert.equal(options.warmups, 3);
  assert.equal(options.measurements, 20);
  assert.equal("beforeImage" in options, false);
  assert.equal("afterImage" in options, false);
});

test("headed/headless mode is parsed explicitly", () => {
  assert.equal(parseArguments([...minimumArguments, "--headless"]).headless, true);
});

test("legacy image path arguments are rejected instead of silently ignored", () => {
  assert.throws(
    () => parseArguments([...minimumArguments, "--before-image", "before.jpg"]),
    /Unexpected argument: --before-image/,
  );
});
