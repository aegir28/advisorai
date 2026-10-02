import { Check, CircleAlert, Minus, X } from "lucide-react";
import type { AnalysisRun, StepStatus } from "@/domain/types";
import { groupRun } from "@/lib/analysis-groups";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";

/** The mark in front of a stage: ✓ done, ● in progress, ○ waiting. */
function Mark({ status }: { status: StepStatus }) {
  const base = "grid size-7 shrink-0 place-items-center rounded-full";
  switch (status) {
    case "done":
      return <span className={cn(base, "bg-primary text-primary-foreground")}><Check aria-hidden className="size-4" /></span>;
    case "warning":
      return <span className={cn(base, "bg-uncertain-soft text-uncertain ring-1 ring-uncertain/40")}><CircleAlert aria-hidden className="size-4" /></span>;
    case "failed":
      return <span className={cn(base, "bg-urgent text-white")}><X aria-hidden className="size-4" /></span>;
    case "running":
      return (
        <span className={cn(base, "ring-2 ring-primary/30")}>
          <span className="size-3 animate-pulse rounded-full bg-primary motion-reduce:animate-none" />
        </span>
      );
    case "skipped":
      return <span className={cn(base, "text-muted-foreground/60")}><Minus aria-hidden className="size-4" /></span>;
    default:
      return <span className={cn(base, "border-2 border-muted-foreground/30")} />;
  }
}

/**
 * Calm, five-stage progress. The internal workflow (14 steps, agents, review
 * passes) stays out of sight. Partial and failed states are explained in plain
 * language and never hidden.
 */
export function RunProgress({ run }: { run: AnalysisRun }) {
  const groups = groupRun(run);
  return (
    <ol aria-label="Review progress" className="space-y-5">
      {groups.map((g) => (
        <li key={g.key} aria-current={g.status === "running" ? "step" : undefined} className="flex items-start gap-4">
          <Mark status={g.status} />
          <div className="min-w-0 flex-1">
            <p className={cn("text-xl leading-7", (g.status === "pending" || g.status === "skipped") && "text-muted-foreground")}>
              {g.title}
              <span className="sr-only"> — {tk(`step.${g.status}`)}</span>
            </p>
            {g.note && <p className="mt-1 text-muted-foreground">{g.note}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
