import { describe, expect, it } from "vitest";
import { evidenceAriaLabel } from "@/lib/evidence-label";

describe("evidenceAriaLabel", () => {
  it("keeps the visible label and adds the statement it supports", () => {
    const name = evidenceAriaLabel("Source", "Troponin I was 182 ng/L.");
    expect(name.startsWith("Source")).toBe(true);
    expect(name).toContain("Troponin I was 182 ng/L.");
  });

  it("never needs an internal id and falls back to the visible label", () => {
    expect(evidenceAriaLabel("Where this comes from")).toBe("Where this comes from");
    expect(evidenceAriaLabel("Source", "   ")).toBe("Source");
  });

  it("shortens very long statements", () => {
    const name = evidenceAriaLabel("Source", "word ".repeat(80));
    expect(name.length).toBeLessThan(160);
    expect(name).toContain("…");
  });
});
