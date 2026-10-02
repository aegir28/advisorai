import type { TimelineData } from "@/domain/types";
import { formatDate, formatMonth } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";
import { FlagMarker, flagSurface } from "./markers";

/** A quiet vertical timeline. Gaps and conflicting dates are marked, never hidden. */
export function TimelineView({ data }: { data: TimelineData }) {
  return (
    <ol className="relative space-y-9 border-l-2 pl-7">
      {data.events.map((e) => {
        const gap = data.gaps.find((g) => g.afterEventId === e.id);
        return (
          <li key={e.id} className="relative space-y-6">
            <span
              aria-hidden
              className={cn(
                "absolute -left-[2.17rem] top-1.5 size-3.5 rounded-full border-[3px] border-background",
                e.conflict ? "bg-disagree" : "bg-primary",
              )}
            />
            <div className="space-y-1.5">
              <p className="text-sm text-muted-foreground">
                {e.precision === "day" ? formatDate(e.date) : formatMonth(e.date)}
                {e.precision === "approx" && " (approximately)"}
              </p>
              <h3 className="text-xl leading-snug">{e.title}</h3>
              <p className="text-muted-foreground">{e.detail}</p>
              <EvidenceChip itemId={e.id} />
              {e.conflict && (
                <div className={cn("mt-3 space-y-1.5 rounded-2xl border p-4 text-sm", flagSurface.disagreement)}>
                  <FlagMarker flag="disagreement" label="Two versions in your records" />
                  <p>{e.conflict}</p>
                </div>
              )}
            </div>
            {gap && (
              <div className={cn("space-y-1.5 rounded-2xl border p-4 text-sm", flagSurface.missing)}>
                <FlagMarker flag="missing" label="Possible gap" />
                <p>{gap.text}</p>
                <EvidenceChip itemId={gap.id} />
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function TimelineChecks({ checks }: { checks: string[] }) {
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">How we checked this timeline</summary>
      <ul className="mt-3 space-y-1 text-muted-foreground">
        {checks.map((c) => <li key={c}>• {c}</li>)}
      </ul>
    </details>
  );
}
