"use client";

import { useParams } from "next/navigation";
import { CircleOff, Route } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ResultsGate } from "@/components/case/results-gate";
import { Legend } from "@/components/medical/legend";
import { FlagMarker } from "@/components/medical/markers";
import { PerspectiveCard } from "@/components/medical/perspective-card";
import { usePerspectives } from "@/features/case/hooks";
import { specialistNames } from "@/mocks/scenarios";

export default function PerspectivesPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = usePerspectives(caseId);
  return (
    <>
      <PageHeader
        eyebrow="Specialist perspectives"
        title="Several specialist views, kept separate"
        description="Only the views that matter for your case were asked, each looking through its own lens. We keep them apart so differences stay visible."
      />
      <ResultsGate query={q} caseId={caseId}>
        {(data) => (
          <div className="space-y-8">
            <section className="paper space-y-4 p-5" aria-labelledby="routing-h">
              <h2 id="routing-h" className="flex items-center gap-2 text-xl"><Route aria-hidden className="size-5 text-primary" /> Why these perspectives?</h2>
              <ul className="grid gap-3 sm:grid-cols-2">
                {data.routing.selected.map((s) => (
                  <li key={s.specialist} className="rounded-xl border bg-card p-3">
                    <p className="flex items-center justify-between gap-2 font-medium">
                      {specialistNames[s.specialist]}
                      <span className="text-xs font-normal text-muted-foreground">{s.priority}</span>
                    </p>
                    <p className="text-sm text-muted-foreground">{s.reason}</p>
                  </li>
                ))}
              </ul>
              {data.routing.notSelected.length > 0 && (
                <div className="space-y-2">
                  <p className="eyebrow flex items-center gap-1.5"><CircleOff aria-hidden className="size-3.5" /> Not asked, and why</p>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {data.routing.notSelected.map((n) => <li key={n.name}><span className="font-medium text-foreground">{n.name}</span>: {n.why}</li>)}
                  </ul>
                </div>
              )}
              {data.routing.missingForRouting.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <FlagMarker flag="missing" />
                  <span>Would help choose perspectives: {data.routing.missingForRouting.join(", ")}.</span>
                </div>
              )}
            </section>

            <Legend />

            <div className="space-y-5">
              {data.reports.map((r) => <PerspectiveCard key={r.id} report={r} />)}
            </div>
          </div>
        )}
      </ResultsGate>
    </>
  );
}
