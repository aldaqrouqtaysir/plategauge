/** Shared UI/session policy. Keep raw length, decimal grammar and numeric bounds identical. */
export const STARTING_MASS_MAX_LENGTH = 64;

export function parseStartingMass(value: string): { text: string; value?: number; error?: string } {
  const text = value.trim();
  if (value.length > STARTING_MASS_MAX_LENGTH) {
    return { text, error: "Use no more than 64 characters for the starting mass, or leave it blank." };
  }
  if (!text) return { text };
  const mass = Number(text);
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text) || !Number.isFinite(mass) || mass <= 0 || mass > 100_000) {
    return { text, error: "Enter a starting mass greater than 0 and no more than 100,000 g, or leave it blank." };
  }
  return { text, value: mass };
}
