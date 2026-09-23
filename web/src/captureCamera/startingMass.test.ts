import { describe, expect, it } from "vitest";
import { parseStartingMass, STARTING_MASS_MAX_LENGTH } from "./startingMass";

describe("shared bounded starting mass policy", () => {
  it.each([["", "", undefined], ["  ", "", undefined], [" 250.50 ", "250.50", 250.5], [".5", ".5", 0.5], ["1.", "1.", 1], ["100000", "100000", 100000]] as const)("parses %j without changing the existing decimal contract", (input, text, value) => {
    expect(parseStartingMass(input)).toEqual(value === undefined ? { text } : { text, value });
  });
  it.each(["0", "-1", "1e3", "0x20", "Infinity", "NaN", "100001", "1,000", "word"])("rejects invalid mass %j", (input) => {
    expect(parseStartingMass(input).error).toMatch(/starting mass/);
  });
  it("applies the existing raw 64-character bound before trimming", () => {
    expect(STARTING_MASS_MAX_LENGTH).toBe(64);
    expect(parseStartingMass("0".repeat(63) + "1")).toEqual({ text: "0".repeat(63) + "1", value: 1 });
    for (const input of ["0".repeat(64) + "1", " ".repeat(64) + "1", " ".repeat(65)]) {
      expect(parseStartingMass(input).error).toContain("64 characters");
    }
  });
});
