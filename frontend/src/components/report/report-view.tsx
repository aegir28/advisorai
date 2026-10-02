"use client";

import { useEffect, useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { PatientReport } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { SectionRenderer } from "./section-renderer";

/**
 * The blueprint's 19 fixed sections stay in the data. People see eight calm
 * groups that open on demand. Group → section numbers:
 */
export const REPORT_GROUPS: { key: string; sections: number[]; open?: boolean }[] = [
  { key: "reportGroup.1", sections: [1], open: true },
  { key: "reportGroup.2", sections: [2, 3], open: true },
  { key: "reportGroup.3", sections: [4, 5, 6, 7, 8] },
  { key: "reportGroup.4", sections: [9, 10, 11, 17] },
  { key: "reportGroup.5", sections: [12, 13, 14] },
  { key: "reportGroup.6", sections: [15, 16] },
  { key: "reportGroup.7", sections: [18] },
  { key: "reportGroup.8", sections: [19] },
];

export function ReportView({ report, caseId }: { report: PatientReport; caseId: string }) {
  const baseId = useId();
  const [open, setOpen] = useState<Record<string, boolean>>(() => Object.fromEntries(REPORT_GROUPS.map((g) => [g.key, !!g.open])));
  const allOpen = REPORT_GROUPS.every((g) => open[g.key]);

  // Printing always shows every section, then restores what was open.
  useEffect(() => {
    let saved: Record<string, boolean> | null = null;
    const before = () => {
      setOpen((cur) => {
        saved = cur;
        return Object.fromEntries(REPORT_GROUPS.map((g) => [g.key, true]));
      });
    };
    const after = () => saved && setOpen(saved);
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  return (
    <div>
      <div className="no-print mb-2 flex justify-end">
        <button
          type="button"
          onClick={() => setOpen(Object.fromEntries(REPORT_GROUPS.map((g) => [g.key, !allOpen])))}
          className="text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          {allOpen ? "Collapse all" : "Expand all"}
        </button>
      </div>
      <div className="divide-y border-y">
        {REPORT_GROUPS.map((g, i) => {
          const sections = g.sections.map((n) => report.sections.find((s) => s.number === n)).filter((s) => !!s);
          if (!sections.length) return null;
          const isOpen = !!open[g.key];
          const panelId = `${baseId}-p${i}`;
          return (
            <section key={g.key} aria-label={tk(g.key)}>
              <h2>
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-controls={panelId}
                  onClick={() => setOpen((cur) => ({ ...cur, [g.key]: !cur[g.key] }))}
                  className="flex w-full items-center gap-4 py-5 text-left"
                >
                  <span className="flex-1 font-heading text-2xl text-ink">{tk(g.key)}</span>
                  <ChevronDown aria-hidden className={cn("size-5 shrink-0 text-muted-foreground transition-transform", isOpen && "rotate-180")} />
                </button>
              </h2>
              <div id={panelId} hidden={!isOpen} className="report-group-body space-y-10 pb-9">
                {sections.map((s) => (
                  <SectionRenderer key={s.number} section={s} caseId={caseId} heading={sections.length > 1 ? "sub" : "none"} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
