"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { UploadDropzone, type FileCheck } from "@/components/case/documents";
import { ResultsGate } from "@/components/case/results-gate";
import { PageIntro } from "@/components/layout/page-intro";
import { ComparisonView } from "@/components/medical/comparison-view";
import { ErrorState, LoadingState } from "@/components/medical/states";
import { Button } from "@/components/ui/button";
import { useCase, useComparison, useQuestions, useSecondOpinion } from "@/features/case/hooks";
import { api } from "@/lib/api";

const SAMPLE_NAME = "Second-opinion consultation note (synthetic).pdf";

export default function SecondOpinionPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const c = useCase(caseId);
  const so = useSecondOpinion(caseId);
  const comparison = useComparison(caseId);
  const questions = useQuestions(caseId);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  // The comparison only exists once the second opinion has been read: refresh it then.
  const soStatus = so.data?.status;
  const reloadComparison = comparison.reload;
  useEffect(() => {
    if (soStatus === "ready") reloadComparison();
  }, [soStatus, reloadComparison]);

  const submit = async (name: string) => {
    setBusy(true);
    await api.submitSecondOpinion(caseId, { name });
    setBusy(false);
  };
  const onFiles = ({ valid, errors: errs }: FileCheck) => {
    setErrors(errs);
    if (valid[0]) void submit(valid[0].name);
  };

  if (so.status === "loading" || c.status === "loading") return <LoadingState rows={2} />;
  if (so.status === "error") return <ErrorState onRetry={so.reload} />;
  const state = so.data!;

  // ── Step 3: your comparison ──
  if (state.status === "ready") {
    return (
      <>
        <PageIntro title="Your comparison">
          What each doctor said, side by side. Added: {state.documentName}.
        </PageIntro>
        <ResultsGate query={comparison} caseId={caseId}>
          {(cmp) => <ComparisonView comparison={cmp} caseId={caseId} questions={questions.data ?? []} />}
        </ResultsGate>
      </>
    );
  }

  // ── Step 2: we're reviewing it ──
  if (state.status === "processing") {
    return (
      <>
        <PageIntro title="We’re reviewing it">Reading the doctor’s opinion and lining it up with your case. Only the new document is read.</PageIntro>
        <div role="status" aria-live="polite" className="flex items-center gap-3 text-lg">
          <span aria-hidden className="size-3 animate-pulse rounded-full bg-primary motion-reduce:animate-none" />
          Comparing…
        </div>
      </>
    );
  }

  // ── Step 1: upload ──
  const hasResults = c.data?.status === "complete" || c.data?.status === "partial";
  return (
    <>
      <PageIntro title="Compare a doctor’s opinion">
        Saw another doctor? Add what they said. We’ll show what agrees, what differs, what’s new and what’s still unresolved. We never pick a winner.
      </PageIntro>
      {!hasResults ? (
        <p className="text-muted-foreground">Once your case has been reviewed, you can add a second opinion here.</p>
      ) : (
        <div className="space-y-8">
          <UploadDropzone onFiles={onFiles} busy={busy} prompt="Upload the doctor’s opinion" />
          {errors.length > 0 && (
            <ul role="alert" className="space-y-1 rounded-2xl bg-uncertain-soft/70 p-4 text-sm">{errors.map((e) => <li key={e}>{e}</li>)}</ul>
          )}
          <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
            <span>Prototype: files aren’t read.</span>
            <Button variant="outline" disabled={busy} onClick={() => submit(SAMPLE_NAME)}>Use a sample doctor’s opinion</Button>
          </div>
        </div>
      )}
    </>
  );
}
