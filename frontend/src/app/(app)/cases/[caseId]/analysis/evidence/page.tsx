"use client";

import { useParams } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { ResultsGate } from "@/components/case/results-gate";
import { BackLink } from "@/components/layout/back-link";
import { PageIntro } from "@/components/layout/page-intro";
import { ClaimRow } from "@/components/medical/claim-row";
import { useEvidence } from "@/features/case/hooks";
import type { VerificationStatus } from "@/domain/types";

const GROUPS: { title: string; hint: string; statuses: VerificationStatus[]; open?: boolean }[] = [
  { title: "Confirmed", hint: "Your reports and the references agree.", statuses: ["supported"], open: true },
  { title: "Partly confirmed", hint: "Some support, with gaps remaining.", statuses: ["partially_supported"] },
  { title: "Couldn’t be confirmed", hint: "Not enough evidence, unclear, or your records say something different.", statuses: ["unclear", "contradicted", "insufficient_evidence"], open: true },
];

export default function EvidencePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = useEvidence(caseId);
  return (
    <>
      <BackLink href={`/cases/${caseId}/analysis`}>Analysis</BackLink>
      <PageIntro title="Supporting evidence">
        Before anything reached your report, each important statement was checked against your own reports and a reference library. Anything we couldn’t trace was removed.
      </PageIntro>
      <ResultsGate query={q} caseId={caseId}>
        {(data) => {
          const title = (id: string) => data.sources.find((s) => s.id === id)?.title ?? id;
          const removed = data.claims.filter((c) => c.removed).length;
          return (
            <div className="space-y-10">
              <p className="text-lg">
                We checked {data.claims.length} statements.
                {removed > 0 && ` ${removed} couldn’t be traced to a source, so we removed ${removed === 1 ? "it" : "them"} before writing your report.`}
              </p>

              <div className="divide-y border-y">
                {GROUPS.map((g) => {
                  const claims = data.claims.filter((c) => g.statuses.includes(c.status));
                  if (!claims.length) return null;
                  return (
                    <details key={g.title} className="group py-1" open={g.open}>
                      <summary className="flex cursor-pointer list-none items-center gap-4 py-4">
                        <div className="min-w-0 flex-1">
                          <h3 className="text-xl">{g.title} <span className="text-muted-foreground">· {claims.length}</span></h3>
                          <p className="text-muted-foreground">{g.hint}</p>
                        </div>
                        <ChevronDown aria-hidden className="size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
                      </summary>
                      <ul className="space-y-6 pb-6">
                        {claims.map((c) => <ClaimRow key={c.id} claim={c} sourceTitle={title} />)}
                      </ul>
                    </details>
                  );
                })}
              </div>

              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Reference library we used</summary>
                <ul className="mt-4 space-y-3 text-muted-foreground">
                  {data.sources.map((s) => (
                    <li key={s.id}>
                      <p className="font-medium text-foreground">{s.title}</p>
                      <p>{s.publisher} · {s.year} · {s.licence}</p>
                    </li>
                  ))}
                  <li className="text-xs">Prototype note: these are synthetic placeholder summaries, not real guidelines or drug labels.</li>
                </ul>
              </details>
            </div>
          );
        }}
      </ResultsGate>
    </>
  );
}
