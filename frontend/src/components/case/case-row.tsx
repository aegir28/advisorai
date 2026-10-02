import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { CaseStatus, CaseSummary } from "@/domain/types";
import { cn } from "@/lib/utils";

/** Plain-language status line shown under a case title. */
export const caseStatusLine: Record<CaseStatus, string> = {
  draft: "Add your reports to begin",
  awaiting_upload: "Add your reports to begin",
  processing: "Reviewing your case…",
  complete: "Report ready",
  partial: "Report ready, with some gaps",
  failed: "Needs your attention",
};

const dot: Record<CaseStatus, string> = {
  draft: "bg-muted-foreground/40",
  awaiting_upload: "bg-muted-foreground/40",
  processing: "bg-fact animate-pulse motion-reduce:animate-none",
  complete: "bg-primary",
  partial: "bg-uncertain",
  failed: "bg-urgent",
};

export function caseTitle(c: Pick<CaseSummary, "title" | "concern">): string {
  return c.title ?? c.concern;
}

/** One case in a list: a title, one quiet status line, and a chevron. */
export function CaseRow({ c }: { c: CaseSummary }) {
  return (
    <Link
      href={`/cases/${c.id}`}
      className="group flex items-center gap-4 rounded-2xl px-4 py-4 transition-colors hover:bg-secondary/70 focus-visible:bg-secondary/70 sm:-mx-4"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate font-heading text-xl text-ink">{caseTitle(c)}</p>
        <p className="mt-0.5 flex items-center gap-2 text-sm text-muted-foreground">
          <span aria-hidden className={cn("size-2 rounded-full", dot[c.status])} />
          {caseStatusLine[c.status]}
        </p>
      </div>
      <ChevronRight aria-hidden className="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}
