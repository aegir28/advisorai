"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { BookMarked } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ResultsGate } from "@/components/case/results-gate";
import { ClaimRow } from "@/components/medical/claim-row";
import { VerificationBadge } from "@/components/medical/markers";
import { useEvidence } from "@/features/case/hooks";
import type { VerificationStatus } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";

const STATUSES: VerificationStatus[] = ["supported", "partially_supported", "unclear", "contradicted", "insufficient_evidence"];

export default function EvidencePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = useEvidence(caseId);
  const [filter, setFilter] = useState<VerificationStatus | "all">("all");

  return (
    <>
      <PageHeader
        eyebrow="Evidence and verification"
        title="How each important claim was checked"
        description="Specialist output is never trusted blindly. Each claim is compared with your own records and a curated reference library. A claim that can’t be traced is removed, and shown here."
      />
      <ResultsGate query={q} caseId={caseId}>
        {(data) => {
          const counts = Object.fromEntries(STATUSES.map((s) => [s, data.claims.filter((c) => c.status === s).length])) as Record<VerificationStatus, number>;
          const removed = data.claims.filter((c) => c.removed).length;
          const shown = filter === "all" ? data.claims : data.claims.filter((c) => c.status === filter);
          const title = (id: string) => data.sources.find((s) => s.id === id)?.title ?? id;
          return (
            <div className="space-y-8">
              <div className="paper space-y-4 p-5">
                <p className="text-sm text-muted-foreground">
                  {data.claims.length} claims checked
                  {removed > 0 && <> · <strong className="font-medium text-foreground">{removed} removed</strong> before the report because the citation couldn’t be resolved</>}
                </p>
                <div role="group" aria-label="Filter claims by status" className="flex flex-wrap gap-2">
                  <button
                    type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}
                    className={cn("rounded-full border px-3 py-1 text-xs font-medium", filter === "all" ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-secondary")}
                  >
                    All · {data.claims.length}
                  </button>
                  {STATUSES.map((s) => (
                    <button
                      key={s} type="button" aria-pressed={filter === s} onClick={() => setFilter(s)} disabled={!counts[s]}
                      className={cn("rounded-full transition-opacity disabled:opacity-40", filter === s && "ring-2 ring-primary ring-offset-2 ring-offset-background")}
                      aria-label={`${tk(`verify.${s}`)}: ${counts[s]}`}
                    >
                      <VerificationBadge status={s} className="pointer-events-none" />
                      <span className="sr-only">{counts[s]}</span>
                    </button>
                  ))}
                </div>
              </div>

              <ul className="space-y-3">
                {shown.map((c) => <ClaimRow key={c.id} claim={c} sourceTitle={title} />)}
              </ul>

              <section aria-labelledby="lib-h" className="space-y-3">
                <h2 id="lib-h" className="flex items-center gap-2 text-xl"><BookMarked aria-hidden className="size-5 text-primary" /> Reference library used</h2>
                <ul className="space-y-3">
                  {data.sources.map((s) => (
                    <li key={s.id} className="paper space-y-1 p-4 text-sm">
                      <p className="font-medium">{s.title}</p>
                      <p className="text-muted-foreground">{s.publisher} · {s.year} · {s.section}</p>
                      <p className="text-xs text-muted-foreground">Licence: {s.licence}</p>
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">
                  Prototype note: these are synthetic placeholder summaries written for the demo. They are not real guidelines or drug labels.
                </p>
              </section>
            </div>
          );
        }}
      </ResultsGate>
    </>
  );
}
