"use client";

import { useParams } from "next/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { ResultsGate } from "@/components/case/results-gate";
import { TimelineChecks, TimelineView } from "@/components/medical/timeline-view";
import { useTimeline } from "@/features/case/hooks";

export default function TimelinePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const timeline = useTimeline(caseId);
  return (
    <>
      <PageHeader
        eyebrow="Timeline"
        title="Your medical history, in order"
        description="Every event links to the page of your own record it came from. Possible gaps and conflicting dates are marked, never hidden."
      />
      <ResultsGate query={timeline} caseId={caseId}>
        {(data) => (
          <div className="space-y-8">
            <TimelineView data={data} />
            <TimelineChecks checks={data.checks} />
          </div>
        )}
      </ResultsGate>
    </>
  );
}
