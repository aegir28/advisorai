/**
 * Browser-history support for a step-by-step wizard. Each step is a real
 * history entry, so the browser Back and Forward buttons move between steps.
 * The step number lives in `history.state`; the URL does not change.
 */
const KEY = "wizardStep";

export function readWizardStep(state: unknown, max: number): number {
  const raw = state && typeof state === "object" ? (state as Record<string, unknown>)[KEY] : undefined;
  return typeof raw === "number" && Number.isInteger(raw) ? Math.min(Math.max(raw, 0), max) : 0;
}

export function withWizardStep(state: unknown, step: number): Record<string, unknown> {
  const base = state && typeof state === "object" ? (state as Record<string, unknown>) : {};
  return { ...base, [KEY]: step };
}
