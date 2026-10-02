"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowRight, CircleCheck, FileUp, LoaderCircle, Stethoscope } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ResultsGate } from "@/components/case/results-gate";
import { UploadDropzone, type FileCheck } from "@/components/case/documents";
import { EvidenceChip } from "@/components/medical/evidence-chip";
import { ErrorState, LoadingState } from "@/components/medical/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { useQuestions, useSecondOpinion } from "@/features/case/hooks";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const SAMPLE_NAME = "Second-opinion consultation note (synthetic).pdf";

export default function SecondOpinionPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const so = useSecondOpinion(caseId);
  const questions = useQuestions(caseId);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const submit = async (name: string) => {
    setBusy(true);
    await api.submitSecondOpinion(caseId, { name });
    setBusy(false);
  };
  const onFiles = ({ valid, errors: errs }: FileCheck) => {
    setErrors(errs);
    if (valid[0]) void submit(valid[0].name);
  };

  if (so.status === "loading") return <LoadingState rows={2} />;
  if (so.status === "error") return <ErrorState onRetry={so.reload} />;
  const state = so.data!;

  return (
    <>
      <PageHeader
        eyebrow="Second opinion"
        title="Add what the second doctor said"
        description="After you’ve seen another doctor, add their note. We read it the same way as your other records and compare the two side by side. We never pick a winner."
      />

      <ResultsGate query={questions} caseId={caseId}>
        {(qs) => {
          const mine = qs.filter((q) => q.audience === "second_opinion_doctor").slice(0, 3);
          return (
            <div className="space-y-8">
              <ol className="grid gap-3 sm:grid-cols-3" aria-label="Second opinion steps">
                {[
                  ["See a second doctor", "Take your questions with you.", Stethoscope],
                  ["Add their note", "A PDF, a photo, or typed notes.", FileUp],
                  ["Compare side by side", "Where you agree, differ, or need more.", CircleCheck],
                ].map(([title, body, Icon], i) => {
                  const I = Icon as typeof Stethoscope;
                  return (
                    <li key={title as string} className="paper flex gap-3 p-4">
                      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-secondary text-secondary-foreground"><I aria-hidden className="size-4.5" /></span>
                      <div>
                        <p className="font-medium">{i + 1}. {title as string}</p>
                        <p className="text-sm text-muted-foreground">{body as string}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>

              {mine.length > 0 && (
                <section className="space-y-3" aria-labelledby="bring">
                  <h2 id="bring" className="text-xl">Questions to bring to the second doctor</h2>
                  <ul className="space-y-2">
                    {mine.map((q) => (
                      <li key={q.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card p-3.5">
                        <p className="min-w-0 flex-1 basis-60">{q.text}</p>
                        <EvidenceChip itemId={q.id} label="Why this question" />
                      </li>
                    ))}
                  </ul>
                  <Link href={`/cases/${caseId}/questions`} className="text-sm font-medium text-primary underline underline-offset-4">See all my questions</Link>
                </section>
              )}

              {state.status === "none" && (
                <section className="space-y-4" aria-labelledby="up-so">
                  <h2 id="up-so" className="text-xl">Add the second opinion</h2>
                  <UploadDropzone onFiles={onFiles} busy={busy} />
                  {errors.length > 0 && (
                    <ul role="alert" className="space-y-1 rounded-xl border border-uncertain/30 bg-uncertain-soft/60 p-3 text-sm">
                      {errors.map((e) => <li key={e}>{e}</li>)}
                    </ul>
                  )}
                  <div className="flex flex-wrap items-center gap-3 rounded-xl border border-dashed p-4">
                    <p className="min-w-0 flex-1 basis-64 text-sm text-muted-foreground">Prototype: files aren’t read. Use a synthetic sample note to see the comparison.</p>
                    <Button variant="outline" size="lg" disabled={busy} onClick={() => submit(SAMPLE_NAME)}>Use the sample second-opinion note</Button>
                  </div>
                </section>
              )}

              {state.status === "processing" && (
                <section role="status" aria-live="polite" className="paper space-y-3 p-5">
                  <h2 className="flex items-center gap-2 text-xl"><LoaderCircle aria-hidden className="size-5 animate-spin text-primary motion-reduce:animate-none" /> Reading the second opinion…</h2>
                  <p className="text-muted-foreground">We’re extracting it like your other records, matching it to your questions, and preparing the comparison. Only the new document is read.</p>
                </section>
              )}

              {state.status === "ready" && (
                <section className="paper flex flex-wrap items-center justify-between gap-4 p-5" aria-labelledby="ready-so">
                  <div>
                    <h2 id="ready-so" className="flex items-center gap-2 text-xl"><CircleCheck aria-hidden className="size-5 text-evidence" /> Second opinion added</h2>
                    <p className="text-sm text-muted-foreground">{state.documentName}</p>
                  </div>
                  <Link href={`/cases/${caseId}/comparison`} className={cn(buttonVariants({ size: "lg" }))}>
                    See the comparison <ArrowRight aria-hidden data-icon="inline-end" />
                  </Link>
                </section>
              )}
            </div>
          );
        }}
      </ResultsGate>
    </>
  );
}
