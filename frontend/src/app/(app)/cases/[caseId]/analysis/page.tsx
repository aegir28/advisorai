"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowRight, FastForward, RefreshCcw, Upload } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, ErrorState, LoadingState, PartialNotice } from "@/components/medical/states";
import { RunProgress } from "@/components/medical/run-progress";
import { Button, buttonVariants } from "@/components/ui/button";
import { useCase, useRun } from "@/features/case/hooks";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { invalidateQueries } from "@/lib/use-query";

export default function AnalysisPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const router = useRouter();
  const c = useCase(caseId);
  const run = useRun(c.data?.runId);
  const [busy, setBusy] = useState(false);

  // The case moves to its final state when the run settles; refresh everything once.
  const runStatus = run.data?.status;
  useEffect(() => {
    if (runStatus && runStatus !== "running") invalidateQueries();
  }, [runStatus]);

  if (c.status === "loading" || (c.data?.runId && run.status === "loading")) return <LoadingState rows={2} />;
  if (c.status === "error" || run.status === "error") return <ErrorState onRetry={() => { c.reload(); run.reload(); }} />;

  if (!c.data?.runId || !run.data) {
    return (
      <>
        <PageHeader eyebrow="Analysis" title="Analysis hasn't started yet" />
        <EmptyState title="Add your records first" body="Once your documents are added, we'll read them and prepare your report." action={{ label: "Add records", href: `/cases/${caseId}/upload` }} />
      </>
    );
  }

  const r = run.data;
  const retry = async () => {
    setBusy(true);
    await api.startAnalysis(caseId, { simulate: "complete" });
    setBusy(false);
  };
  const skip = async () => {
    await api.skipToResults(r.id);
  };

  return (
    <>
      <PageHeader
        eyebrow="Analysis"
        title={r.status === "running" ? "Reading your records…" : r.status === "failed" ? "We had to stop" : r.status === "partial" ? "Your analysis is ready, with gaps" : "Your analysis is ready"}
        description={
          r.status === "running"
            ? "Each step below is saved as it finishes. Real analyses take 2–6 minutes; this prototype takes about 20 seconds."
            : r.status === "failed"
              ? "Nothing is hidden: here is exactly where it stopped, and what would help."
              : "Everything below was checked against your records. Gaps, if any, are listed rather than smoothed over."
        }
        actions={
          r.status === "running" ? (
            <Button variant="outline" onClick={skip}><FastForward aria-hidden data-icon="inline-start" /> Skip to results</Button>
          ) : undefined
        }
      />

      <div className="space-y-6">
        {r.status === "failed" && r.failure && (
          <div role="alert" className="space-y-4 rounded-2xl border border-urgent/30 bg-urgent-soft p-5">
            <h2 className="text-xl">{r.failure.title}</h2>
            <p>{r.failure.body}</p>
            <div className="flex flex-wrap gap-3">
              <Button onClick={retry} disabled={busy}><RefreshCcw aria-hidden data-icon="inline-start" /> Try the analysis again</Button>
              <Link href={`/cases/${caseId}/documents`} className={cn(buttonVariants({ variant: "outline" }))}>
                <Upload aria-hidden data-icon="inline-start" /> Review my documents
              </Link>
            </div>
          </div>
        )}

        {r.status === "partial" && (
          <PartialNotice title="Some parts could not be completed">
            <ul className="mt-1 list-disc space-y-1 pl-4">
              {r.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
            <p className="mt-2">The report shows these gaps wherever they matter. Nothing was guessed.</p>
          </PartialNotice>
        )}

        <div className="paper p-5 sm:p-6">
          <RunProgress run={r} />
        </div>

        {(r.status === "complete" || r.status === "partial") && (
          <div className="flex flex-wrap gap-3">
            <Link href={`/cases/${caseId}/timeline`} className={cn(buttonVariants({ size: "lg" }))}>
              See your timeline <ArrowRight aria-hidden data-icon="inline-end" />
            </Link>
            <Link href={`/cases/${caseId}/report`} className={cn(buttonVariants({ size: "lg", variant: "outline" }))}>
              Go straight to the report
            </Link>
            <Button variant="ghost" size="lg" onClick={() => router.push(`/cases/${caseId}/questions`)}>See my questions</Button>
          </div>
        )}
      </div>
    </>
  );
}
