"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowRight, FlaskConical, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { DocumentList, UploadDropzone, type FileCheck } from "@/components/case/documents";
import { EmptyState, ErrorState, LoadingState, PartialNotice } from "@/components/medical/states";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { RunOutcome, ScenarioId } from "@/domain/types";
import { useCase, useDocuments } from "@/features/case/hooks";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
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

  if (c.status === "loading" || docs.status === "loading") return <LoadingState rows={3} />;
  if (c.status === "error" || docs.status === "error") return <ErrorState onRetry={() => { c.reload(); docs.reload(); }} />;
  if (!c.data) return null;

  const done = c.data.status === "complete" || c.data.status === "partial";
  const selected = scenario ?? c.data.scenario;
  const documents = docs.data ?? [];

  const addFiles = async ({ valid, errors: errs }: FileCheck) => {
    setErrors(errs);
    if (!valid.length) return;
    setBusy(true);
    for (const f of valid) await api.uploadDocument(caseId, { name: f.name, sizeKb: Math.max(1, Math.round(f.size / 1024)) });
    setBusy(false);
    docs.reload();
    c.reload();
  };

  const useSample = async () => {
    setBusy(true);
    await api.attachSampleRecords(caseId, selected);
    setBusy(false);
    docs.reload();
    c.reload();
  };

  const start = async () => {
    setBusy(true);
    await api.attachSampleRecords(caseId, selected).catch(() => undefined);
    await api.startAnalysis(caseId, simulate === "auto" ? undefined : { simulate });
    router.push(`/cases/${caseId}/analysis`);
  };

  if (done) {
    return (
      <>
        <PageHeader eyebrow="Records" title="Your records were analysed" description="These are the documents behind your results." />
        <DocumentList documents={documents} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="New case · step 2 of 3"
        title="Add your records"
        description="Reports, prescriptions, scans, discharge notes. Files stay private to your case."
      />

      <div className="space-y-8">
        <p className="flex items-center gap-2 rounded-xl bg-secondary/70 px-4 py-3 text-sm">
          <ShieldCheck aria-hidden className="size-4 shrink-0 text-primary" />
          Safety check passed. Nothing urgent was found, so you can continue.
        </p>

        <PartialNotice title="Prototype: your files are not read">
          This demo can’t read real files, and it should never receive real medical information. Choose a synthetic sample case below; the
          analysis will use it. You can still try the upload box to see file checks.
        </PartialNotice>

        <section aria-labelledby="sample-h" className="space-y-4">
          <h2 id="sample-h" className="text-xl">Use synthetic sample records</h2>
          <RadioGroup value={selected} onValueChange={(v) => setScenario(v as ScenarioId)} className="grid gap-3 md:grid-cols-3" aria-label="Sample case">
            {scenarioList.map((s) => {
              const meta = scenarioBlurbs[s.id];
              return (
                <label
                  key={s.id}
                  className={cn("paper flex cursor-pointer flex-col gap-2 p-4 transition-colors has-data-checked:border-primary has-data-checked:bg-accent/50")}
                >
                  <span className="flex items-center gap-2">
                    <RadioGroupItem value={s.id} />
                    <span className="font-medium">{meta.title}</span>
                  </span>
                  <span className="text-sm text-muted-foreground">{meta.blurb}</span>
                  <span className="mt-auto text-xs text-muted-foreground">
                    {s.seedCase.ageYears}, {s.seedCase.sex === "F" ? "female" : "male"} · {s.documents.length} documents · fictional
                  </span>
                </label>
              );
            })}
          </RadioGroup>
          <Button variant="outline" size="lg" onClick={useSample} disabled={busy}>
            Add these sample records
          </Button>
        </section>

        <section aria-labelledby="up-h" className="space-y-4">
          <h2 id="up-h" className="text-xl">Or try the upload box</h2>
          <UploadDropzone onFiles={addFiles} busy={busy} />
          {errors.length > 0 && (
            <ul role="alert" className="space-y-1 rounded-xl border border-uncertain/30 bg-uncertain-soft/60 p-3 text-sm">
              {errors.map((e) => <li key={e}>{e}</li>)}
            </ul>
          )}
        </section>

        <section aria-labelledby="list-h" className="space-y-4">
          <h2 id="list-h" className="text-xl">Your documents ({documents.length})</h2>
          {documents.length === 0 ? (
            <EmptyState title="No documents yet" body="Add the sample records above, or choose files, to continue." />
          ) : (
            <DocumentList
              documents={documents}
              onRemove={async (id) => { await api.removeDocument(caseId, id); docs.reload(); c.reload(); }}
            />
          )}
        </section>

        <details className="no-print rounded-xl border border-dashed p-4 text-sm">
          <summary className="flex cursor-pointer items-center gap-2 font-medium">
            <FlaskConical aria-hidden className="size-4" /> Prototype controls
          </summary>
          <div className="mt-3 space-y-2">
            <p className="text-muted-foreground">Choose how the simulated analysis should end, to experience partial and failed states.</p>
            <RadioGroup value={simulate} onValueChange={(v) => setSimulate(v as RunOutcome | "auto")} className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Simulated outcome">
              {([["auto", "As the sample case would"], ["complete", "Everything works"], ["partial", "Finishes with gaps"], ["failed", "A critical step fails"]] as const).map(([v, l]) => (
                <label key={v} className="flex cursor-pointer items-center gap-2"><RadioGroupItem value={v} /> {l}</label>
              ))}
            </RadioGroup>
          </div>
        </details>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-6">
          <p className="text-sm text-muted-foreground">Next: we read your records. In this prototype that takes about 20 seconds.</p>
          <Button size="lg" onClick={start} disabled={busy || documents.length === 0}>
            Start analysis <ArrowRight aria-hidden data-icon="inline-end" />
          </Button>
        </div>
      </div>
    </>
  );
}
