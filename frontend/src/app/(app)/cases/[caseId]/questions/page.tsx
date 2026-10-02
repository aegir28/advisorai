"use client";

import { useParams } from "next/navigation";
import { ListChecks, Printer } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ResultsGate } from "@/components/case/results-gate";
import { QuestionList } from "@/components/medical/question-list";
import { Button } from "@/components/ui/button";
import { useQuestions } from "@/features/case/hooks";
import { api } from "@/lib/api";

export default function QuestionsPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = useQuestions(caseId);

  return (
    <>
      <PageHeader
        eyebrow="Questions"
        title="Questions made from your own records"
        description="Built from the gaps, conflicts and proposed treatment in your case. Not a generic list. Take them to your visit and mark them off as you go."
        actions={
          <Button variant="outline" size="lg" onClick={() => window.print()}>
            <Printer aria-hidden data-icon="inline-start" /> Print my questions
          </Button>
        }
      />
      <ResultsGate query={q} caseId={caseId}>
        {(questions) => {
          const answered = questions.filter((x) => x.status === "answered").length;
          const partial = questions.filter((x) => x.status === "partially_answered").length;
          return (
            <div className="space-y-6">
              <div className="paper flex flex-wrap items-center gap-4 p-4">
                <span className="grid size-10 place-items-center rounded-xl bg-secondary text-secondary-foreground"><ListChecks aria-hidden className="size-5" /></span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{answered} of {questions.length} answered{partial > 0 && ` · ${partial} partly answered`}</p>
                  <div role="progressbar" aria-label="Questions answered" aria-valuemin={0} aria-valuemax={questions.length} aria-valuenow={answered} className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${(answered / Math.max(1, questions.length)) * 100}%` }} />
                  </div>
                </div>
              </div>
              <QuestionList questions={questions} onChange={(id, patch) => void api.updateQuestion(caseId, id, patch)} />
            </div>
          );
        }}
      </ResultsGate>
    </>
  );
}
