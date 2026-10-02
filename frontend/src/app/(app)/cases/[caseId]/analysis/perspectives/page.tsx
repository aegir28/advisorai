"use client";

import { useParams } from "next/navigation";
import { ResultsGate } from "@/components/case/results-gate";
import { BackLink } from "@/components/layout/back-link";
import { PageIntro } from "@/components/layout/page-intro";
import { PerspectiveCard } from "@/components/medical/perspective-card";
import { usePerspectives } from "@/features/case/hooks";

export default function PerspectivesPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = usePerspectives(caseId);
  return (
    <>
      <BackLink href={`/cases/${caseId}/analysis`}>Analysis</BackLink>
      <PageIntro title="Specialist perspectives">
        We looked at your case from several medical perspectives. Open any one to read it. They are kept separate, so differences stay visible.
      </PageIntro>
      <ResultsGate query={q} caseId={caseId}>
        {(data) => (
          <div className="space-y-10">
            <div className="divide-y border-y">
              {data.reports.map((r) => <PerspectiveCard key={r.id} report={r} />)}
            </div>

            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Why these perspectives?</summary>
              <div className="mt-4 space-y-4 text-muted-foreground">
                <ul className="space-y-2">
                  {data.routing.selected.map((s) => (
                    <li key={s.specialist}><span className="font-medium text-foreground">{s.specialist.replace(/_/g, " ")}</span>: {s.reason}</li>
                  ))}
                </ul>
                {data.routing.notSelected.length > 0 && (
                  <p>Not needed here: {data.routing.notSelected.map((n) => `${n.name} (${n.why.toLowerCase().replace(/\.$/, "")})`).join("; ")}.</p>
                )}
                {data.routing.missingForRouting.length > 0 && <p>Would help us choose better: {data.routing.missingForRouting.join(", ")}.</p>}
              </div>
            </details>
          </div>
        )}
      </ResultsGate>
    </>
  );
}
