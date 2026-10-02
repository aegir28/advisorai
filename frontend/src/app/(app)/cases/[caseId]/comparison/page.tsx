"use client";

import { useParams } from "next/navigation";
import { GitCompareArrows } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ComparisonView } from "@/components/medical/comparison-view";
import { EmptyState, ErrorState, LoadingState } from "@/components/medical/states";
import { useComparison, useQuestions, useSecondOpinion } from "@/features/case/hooks";

export default function ComparisonPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const cmp = useComparison(caseId);
  const so = useSecondOpinion(caseId);
  const questions = useQuestions(caseId);

  const loading = cmp.status === "loading" || so.status === "loading" || questions.status === "loading";

  return (
    <>
      <PageHeader
        eyebrow="Comparison"
        title="Two opinions, side by side"
        description="What each doctor said, the evidence behind each view, and what still needs clarifying. Not a verdict."
      />
      {loading && <LoadingState rows={3} />}
      {cmp.status === "error" && <ErrorState onRetry={cmp.reload} />}
      {!loading && cmp.status === "success" && !cmp.data && (
        <EmptyState
          icon={GitCompareArrows}
          title={so.data?.status === "processing" ? "Almost there…" : "No second opinion yet"}
          body={
            so.data?.status === "processing"
              ? "We’re reading the second opinion. This page fills in as soon as it’s ready."
              : "Add what the second doctor said and we’ll compare it with your first opinion side by side."
          }
          action={{ label: "Add a second opinion", href: `/cases/${caseId}/second-opinion` }}
        />
      )}
      {cmp.data && <ComparisonView comparison={cmp.data} caseId={caseId} questions={questions.data ?? []} />}
    </>
  );
}
