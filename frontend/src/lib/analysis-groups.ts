import type { AnalysisRun, StepStatus } from "@/domain/types";

/**
 * The standard analysis has 14 internal steps (other workflows may have fewer). A patient sees five calm stages.
 * This is purely a presentation mapping; the run data is untouched.
 */
export interface AnalysisGroup {
  key: string;
  title: string;
  status: StepStatus;
  note?: string;
}

const GROUPS: { key: string; title: string; steps: number[] }[] = [
  { key: "documents", title: "Your documents", steps: [1, 2, 3, 4] },
  { key: "history", title: "Your medical history", steps: [5] },
  { key: "perspectives", title: "Specialist perspectives", steps: [6, 7, 8] },
  { key: "evidence", title: "Supporting evidence", steps: [9, 10] },
  { key: "summary", title: "Preparing your summary", steps: [11, 12, 13, 14] },
];

export function groupRun(run: AnalysisRun): AnalysisGroup[] {
  return GROUPS.filter((g) => run.steps.some((s) => g.steps.includes(s.n))).map((g) => {
    const steps = run.steps.filter((s) => g.steps.includes(s.n));
    const has = (st: StepStatus) => steps.some((s) => s.status === st);
    const all = (st: StepStatus) => steps.every((s) => s.status === st);

    let status: StepStatus;
    if (has("failed")) status = "failed";
    else if (all("skipped")) status = "skipped";
    else if (all("pending")) status = "pending";
    else if (has("running") || has("pending")) status = "running";
    else status = has("warning") ? "warning" : "done";

    return { key: g.key, title: g.title, status, note: steps.find((s) => s.note && (s.status === "warning" || s.status === "failed"))?.note };
  });
}
