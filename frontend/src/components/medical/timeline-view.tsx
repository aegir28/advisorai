import { CalendarClock } from "lucide-react";
import type { TimelineData } from "@/domain/types";
import { formatDate, formatMonth } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";
import { FlagMarker, flagSurface } from "./markers";

/** Vertical timeline of dated facts, with gaps and conflicts kept visible. */
export function TimelineView({ data }: { data: TimelineData }) {
  return (
    <ol className="relative space-y-4 before:absolute before:inset-y-2 before:left-[0.95rem] before:w-px before:bg-border sm:before:left-[7.7rem]">
      {data.events.map((e) => {
        const gap = data.gaps.find((g) => g.afterEventId === e.id);
        return (
          <li key={e.id} className="space-y-4">
            <div className="relative grid gap-2 pl-10 sm:grid-cols-[7rem_1fr] sm:gap-6 sm:pl-0">
              <p className="text-sm font-medium text-muted-foreground sm:pr-4 sm:text-right sm:pt-4">
                {e.precision === "day" ? formatDate(e.date) : formatMonth(e.date)}
                {e.precision === "approx" && <span className="block text-xs font-normal">approximate</span>}
              </p>
              <span
                aria-hidden
                className={cn(
                  "absolute left-[0.45rem] top-1.5 size-3 rounded-full border-2 border-background ring-2 sm:left-[7.2rem] sm:top-5",
                  e.conflict ? "bg-disagree ring-disagree/40" : "bg-primary ring-primary/30",
                )}
              />
              <div className={cn("paper space-y-2 p-4 sm:ml-4", e.conflict && "border-disagree/30")}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="text-lg leading-snug">{e.title}</h3>
                  <EvidenceChip itemId={e.id} />
                </div>
                <p className="text-muted-foreground">{e.detail}</p>
                {e.conflict && (
                  <div className={cn("space-y-1.5 rounded-xl border p-3 text-sm", flagSurface.disagreement)}>
                    <FlagMarker flag="disagreement" label="Two versions in your records" />
                    <p>{e.conflict}</p>
                  </div>
                )}
              </div>
            </div>
            {gap && (
              <div className="relative grid gap-2 pl-10 sm:grid-cols-[7rem_1fr] sm:gap-6 sm:pl-0">
                <span aria-hidden className="absolute left-[0.45rem] top-3 size-3 rounded-full border-2 border-dashed border-missing bg-background sm:left-[7.2rem]" />
                <span aria-hidden className="hidden sm:block" />
                <div className={cn("space-y-1.5 rounded-xl border p-3 text-sm sm:ml-4", flagSurface.missing)}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <FlagMarker flag="missing" label="Possible gap" />
                    <EvidenceChip itemId={gap.id} />
                  </div>
                  <p>{gap.text}</p>
                </div>
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
    <div className="paper space-y-2 p-4">
      <p className="eyebrow flex items-center gap-1.5">
        <CalendarClock aria-hidden className="size-3.5" /> Timeline checks (rule-based)
      </p>
      <ul className="space-y-1 text-sm text-muted-foreground">
        {checks.map((c) => <li key={c}>• {c}</li>)}
      </ul>
    </div>
  );
}
