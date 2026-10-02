"use client";

import { useParams } from "next/navigation";
import { ResultsGate } from "@/components/case/results-gate";
import { BackLink } from "@/components/layout/back-link";
import { PageIntro } from "@/components/layout/page-intro";
import { TimelineChecks, TimelineView } from "@/components/medical/timeline-view";
import { useTimeline } from "@/features/case/hooks";

export default function TimelinePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const timeline = useTimeline(caseId);
  return (
    <>
      <BackLink href={`/cases/${caseId}/analysis`}>Analysis</BackLink>
      <PageIntro title="Your medical timeline">Your history in order. Each event links to the page of your own report it came from.</PageIntro>
      <ResultsGate query={timeline} caseId={caseId}>
        {(data) => (
          <div className="space-y-10">
            <TimelineView data={data} />
            <TimelineChecks checks={data.checks} />
          </div>
        )}
      </ResultsGate>
    </>
  );
}
