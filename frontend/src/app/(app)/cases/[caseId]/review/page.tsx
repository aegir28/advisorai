"use client";

import { useParams } from "next/navigation";
import { Scale } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ResultsGate } from "@/components/case/results-gate";
import { DisagreementMatrix } from "@/components/medical/disagreement-matrix";
import { useCrossReview } from "@/features/case/hooks";

export default function ReviewPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = useCrossReview(caseId);
  return (
    <>
      <PageHeader
        eyebrow="Cross-agent review"
        title="Where the specialist views agree, and where they differ"
        description="After each specialist finishes, their findings are compared topic by topic before anything reaches your report."
      />
      <ResultsGate query={q} caseId={caseId}>
        {(data) => (
          <div className="space-y-6">
            <aside className="flex gap-3 rounded-2xl border border-primary/15 bg-accent/60 p-4 text-sm">
              <Scale aria-hidden className="mt-0.5 size-5 shrink-0 text-primary" />
              <p>
                <strong className="font-medium">No forced consensus.</strong> A majority does not win: several perspectives agreeing is not
                treated as evidence. Where views differ, both are kept with their reasoning, and you see them as perspectives to discuss, not as
                a verdict.
              </p>
            </aside>
            <DisagreementMatrix data={data} />
          </div>
        )}
      </ResultsGate>
    </>
  );
}
