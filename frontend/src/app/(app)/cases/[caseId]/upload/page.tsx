"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowRight, FlaskConical } from "lucide-react";
import { DocumentList, UploadDropzone, type FileCheck } from "@/components/case/documents";
import { PageIntro } from "@/components/layout/page-intro";
import { ErrorState, LoadingState } from "@/components/medical/states";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { RunOutcome, ScenarioId } from "@/domain/types";
import { useCase, useDocuments } from "@/features/case/hooks";
import { api } from "@/lib/api";
import { scenarioBlurbs, scenarioList } from "@/mocks/scenarios";

export default function UploadPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const router = useRouter();
  const c = useCase(caseId);
  const docs = useDocuments(caseId);
  const [scenario, setScenario] = useState<ScenarioId | null>(null);
  const [simulate, setSimulate] = useState<RunOutcome | "auto">("auto");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  if (c.status === "loading" || docs.status === "loading") return <LoadingState rows={2} />;
  if (c.status === "error" || docs.status === "error") return <ErrorState onRetry={() => { c.reload(); docs.reload(); }} />;
  if (!c.data) return null;

  const done = c.data.status === "complete" || c.data.status === "partial";
  const selected = scenario ?? c.data.scenario;
  const documents = docs.data ?? [];

  if (done) {
    return (
      <>
        <PageIntro title="Your reports">These are the documents your results are based on.</PageIntro>
        <DocumentList documents={documents} />
      </>
    );
  }

  const addFiles = async ({ valid, errors: errs }: FileCheck) => {
    setErrors(errs);
    if (!valid.length) return;
    setBusy(true);
    for (const f of valid) await api.uploadDocument(caseId, { name: f.name, sizeKb: Math.max(1, Math.round(f.size / 1024)) });
    setBusy(false);
  };

  const start = async () => {
    setBusy(true);
    await api.attachSampleRecords(caseId, selected).catch(() => undefined);
    await api.startAnalysis(caseId, simulate === "auto" ? undefined : { simulate });
    router.push(`/cases/${caseId}/analysis`);
  };

  return (
    <div className="space-y-10">
      <PageIntro title="Add your reports">Reports, scans, prescriptions or discharge notes. Add whatever you have.</PageIntro>

      <UploadDropzone onFiles={addFiles} busy={busy} />
      {errors.length > 0 && (
        <ul role="alert" className="space-y-1 rounded-2xl bg-uncertain-soft/70 p-4 text-sm">
          {errors.map((e) => <li key={e}>{e}</li>)}
        </ul>
      )}

      {documents.length > 0 && (
        <section aria-labelledby="added" className="space-y-3">
          <h3 id="added" className="text-lg">Added so far</h3>
          <DocumentList documents={documents} onRemove={async (id) => { await api.removeDocument(caseId, id); }} />
        </section>
      )}

      <details className="no-print rounded-2xl border border-dashed p-4 text-sm" open={documents.length === 0}>
        <summary className="flex cursor-pointer items-center gap-2 font-medium">
          <FlaskConical aria-hidden className="size-4" /> No reports handy? Try a sample case (prototype)
        </summary>
        <div className="mt-4 space-y-4">
          <p className="text-muted-foreground">
            This prototype can’t read real files, and should never receive real medical information. Pick a fictional sample; your case will
            use it.
          </p>
          <RadioGroup value={selected} onValueChange={(v) => setScenario(v as ScenarioId)} className="grid gap-2" aria-label="Sample case">
            {scenarioList.map((s) => (
              <label key={s.id} className="flex cursor-pointer items-start gap-3 rounded-xl border bg-card p-3.5 has-data-checked:border-primary has-data-checked:bg-accent/40">
                <RadioGroupItem value={s.id} className="mt-1" />
                <span>
                  <span className="block font-medium">{scenarioBlurbs[s.id].title}</span>
                  <span className="block text-muted-foreground">{scenarioBlurbs[s.id].blurb}</span>
                </span>
              </label>
            ))}
          </RadioGroup>
          <Button variant="outline" disabled={busy} onClick={async () => { setBusy(true); await api.attachSampleRecords(caseId, selected); setBusy(false); }}>
            Add these sample reports
          </Button>

          <div className="space-y-2 border-t pt-4">
            <p className="font-medium">How should the simulated review end?</p>
            <RadioGroup value={simulate} onValueChange={(v) => setSimulate(v as RunOutcome | "auto")} className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Simulated outcome">
              {([["auto", "As the sample would"], ["complete", "All goes well"], ["partial", "Finishes with gaps"], ["failed", "Something fails"]] as const).map(([v, l]) => (
                <label key={v} className="flex cursor-pointer items-center gap-2"><RadioGroupItem value={v} /> {l}</label>
              ))}
            </RadioGroup>
          </div>
        </div>
      </details>

      <div className="space-y-3">
        <Button size="lg" className="h-14 w-full rounded-2xl text-base sm:w-auto sm:px-8" onClick={start} disabled={busy || documents.length === 0}>
          Review my case <ArrowRight aria-hidden data-icon="inline-end" />
        </Button>
        <p className="text-sm text-muted-foreground">We’ll review your reports and prepare a clear summary. It usually takes a few minutes.</p>
      </div>
    </div>
  );
}
