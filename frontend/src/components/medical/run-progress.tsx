import { CircleAlert, CircleCheck, CircleX, LoaderCircle, Minus, Circle, type LucideIcon } from "lucide-react";
import type { AnalysisRun, StepStatus } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";

const style: Record<StepStatus, { icon: LucideIcon; cls: string; spin?: boolean }> = {
  pending: { icon: Circle, cls: "text-muted-foreground/50" },
  running: { icon: LoaderCircle, cls: "text-primary", spin: true },
  done: { icon: CircleCheck, cls: "text-evidence" },
  warning: { icon: CircleAlert, cls: "text-uncertain" },
  failed: { icon: CircleX, cls: "text-urgent" },
  skipped: { icon: Minus, cls: "text-muted-foreground/60" },
};

/**
 * Generic run progress. Renders any workflow's steps, including partial
 * (done with a note), failed and skipped, so no step ever fails silently.
 */
export function RunProgress({ run }: { run: AnalysisRun }) {
  const pct = Math.round(run.progress * 100);
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <div className="flex items-baseline justify-between text-sm">
          <span className="font-medium">{pct}% complete</span>
          <span className="text-muted-foreground">Run {run.id}</span>
        </div>
        <div
          role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Analysis progress"
          className="h-2 overflow-hidden rounded-full bg-muted"
        >
          <div
            className={cn("h-full rounded-full transition-all duration-700", run.status === "failed" ? "bg-urgent" : run.status === "partial" ? "bg-uncertain" : "bg-primary")}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <ol className="space-y-1" aria-label="Analysis steps">
        {run.steps.map((s) => {
          const { icon: Icon, cls, spin } = style[s.status];
          return (
            <li
              key={s.n}
              aria-current={s.status === "running" ? "step" : undefined}
              className={cn(
                "flex items-start gap-3 rounded-xl px-3 py-2.5",
                s.status === "running" && "bg-accent",
                s.status === "warning" && "bg-uncertain-soft/60",
                s.status === "failed" && "bg-urgent-soft",
              )}
            >
              <Icon aria-hidden className={cn("mt-0.5 size-5 shrink-0", cls, spin && "animate-spin motion-reduce:animate-none")} />
              <div className="min-w-0 flex-1">
                <p className={cn("font-medium", (s.status === "pending" || s.status === "skipped") && "text-muted-foreground")}>
                  {tk(`run.s${s.n}`)}
                </p>
                {s.note && <p className="text-sm text-muted-foreground">{s.note}</p>}
              </div>
              <span className={cn("shrink-0 text-xs", cls)}>{tk(`step.${s.status}`)}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
