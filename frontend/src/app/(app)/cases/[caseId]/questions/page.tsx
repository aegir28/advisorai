"use client";

import { useParams } from "next/navigation";
import { Printer } from "lucide-react";
import { ResultsGate } from "@/components/case/results-gate";
import { PageIntro } from "@/components/layout/page-intro";
import { QuestionList } from "@/components/medical/question-list";
import { Button } from "@/components/ui/button";
import { useQuestions } from "@/features/case/hooks";
import { api } from "@/lib/api";

export default function QuestionsPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = useQuestions(caseId);

  return (
    <>
      <PageIntro
        title="Questions to take to your doctor"
        action={
          q.data ? (
            <Button variant="outline" onClick={() => window.print()}>
              <Printer aria-hidden data-icon="inline-start" /> Print
            </Button>
          ) : undefined
        }
      >
        Made from your own reports: the gaps, the unclear parts and the treatment you were offered. Bring them to your visit and mark them off as you go.
      </PageIntro>
      <ResultsGate query={q} caseId={caseId}>
        {(questions) => {
          const answered = questions.filter((x) => x.status === "answered").length;
          return (
            <div className="space-y-6">
              <p className="text-muted-foreground" aria-live="polite">{answered} of {questions.length} answered</p>
              <QuestionList questions={questions} onChange={(id, patch) => void api.updateQuestion(caseId, id, patch)} />
            </div>
          );
        }}
      </ResultsGate>
    </>
  );
}
