import { describe, expect, it } from "vitest";
import { readWizardStep, withWizardStep } from "@/lib/wizard-history";

describe("wizard history state", () => {
  it("round-trips a step and keeps unrelated history state (such as the router's)", () => {
    const state = withWizardStep({ __NA: true, tree: [1] }, 2);
    expect(state).toMatchObject({ __NA: true, tree: [1], wizardStep: 2 });
    expect(readWizardStep(state, 3)).toBe(2);
  });

  it("falls back to the first step for missing or invalid state", () => {
    expect(readWizardStep(null, 3)).toBe(0);
    expect(readWizardStep({}, 3)).toBe(0);
    expect(readWizardStep({ wizardStep: "2" }, 3)).toBe(0);
    expect(readWizardStep({ wizardStep: 1.5 }, 3)).toBe(0);
  });

  it("clamps to the valid range", () => {
    expect(readWizardStep({ wizardStep: 9 }, 3)).toBe(3);
    expect(readWizardStep({ wizardStep: -4 }, 3)).toBe(0);
  });
});
