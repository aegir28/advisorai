"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowRight,
  ClipboardList,
  FileText,
  GitCompareArrows,
  Layers,
  ListChecks,
  Route,
  ScanSearch,
  Trash2,
  Upload,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { EvidenceChip } from "@/components/medical/evidence-chip";
import { Legend } from "@/components/medical/legend";
import { FlagMarker, flagSurface } from "@/components/medical/markers";
import { ErrorState, LoadingState, PartialNotice } from "@/components/medical/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useCaseOverview, useRun } from "@/features/case/hooks";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const QUICK_LINKS = [
  { path: "/report", icon: FileText, title: "Your report", body: "The full plain-language report, in 19 sections." },
  { path: "/questions", icon: ListChecks, title: "Your questions", body: "Prioritised questions to take to your doctors." },
  { path: "/timeline", icon: Route, title: "Medical timeline", body: "Your history in order, with gaps marked." },
  { path: "/perspectives", icon: Layers, title: "Specialist perspectives", body: "Each specialist view, kept separate." },
  { path: "/evidence", icon: ScanSearch, title: "Evidence and verification", body: "How each claim was checked." },
  { path: "/second-opinion", icon: GitCompareArrows, title: "Second opinion", body: "Add it later and compare side by side." },
];

export default function CaseOverviewPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const router = useRouter();
  const overview = useCaseOverview(caseId);
  const run = useRun(overview.data?.summary.runId);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (overview.status === "loading") return <LoadingState rows={3} />;
  if (overview.status === "error") return <ErrorState onRetry={overview.reload} />;
  const o = overview.data;
  if (!o) return null;
  const { summary: c } = o;
  const attention = o.documents.filter((d) => d.status === "needs_attention").length;

  return (
    <>
      <PageHeader eyebrow={`Case ${c.code}`} title={c.concern} description={c.proposedTreatment && <>Proposed: <span className="text-foreground">{c.proposedTreatment}</span></>} />

      {(c.status === "draft" || c.status === "awaiting_upload") && (
        <div className="paper mb-8 flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <h2 className="text-xl">Next: add your records</h2>
            <p className="text-muted-foreground">We need documents before we can prepare anything for you.</p>
          </div>
          <Link href={`/cases/${caseId}/upload`} className={cn(buttonVariants({ size: "lg" }))}>
            <Upload aria-hidden data-icon="inline-start" /> Add records
          </Link>
        </div>
      )}

      {c.status === "processing" && (
        <div className="paper mb-8 flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <h2 className="text-xl">We’re reading your records</h2>
            <p className="text-muted-foreground">Follow along as each step finishes.</p>
          </div>
          <Link href={`/cases/${caseId}/analysis`} className={cn(buttonVariants({ size: "lg" }))}>
            View progress <ArrowRight aria-hidden data-icon="inline-end" />
          </Link>
        </div>
      )}

      {c.status === "failed" && (
        <div role="alert" className="mb-8 rounded-2xl border border-urgent/30 bg-urgent-soft p-5">
          <h2 className="text-xl">The analysis couldn’t be finished</h2>
          <p className="mb-3 text-muted-foreground">One document needs a clearer copy. See exactly what happened and try again.</p>
          <Link href={`/cases/${caseId}/analysis`} className={cn(buttonVariants())}>See what happened</Link>
        </div>
      )}

      {c.status === "partial" && (
        <div className="mb-8">
          <PartialNotice title="Your analysis is ready, with some gaps">
            {run.data?.warnings.length ? (
              <ul className="mt-1 list-disc space-y-1 pl-4">{run.data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            ) : (
              "Some parts could not be completed. The report says so wherever it matters."
            )}
          </PartialNotice>
        </div>
      )}

      {o.highlights.length > 0 && (
        <section aria-labelledby="stands-out" className="mb-10 space-y-4">
          <h2 id="stands-out" className="text-2xl">What stands out</h2>
          <ul className="space-y-3">
            {o.highlights.map((h) => (
              <li
                key={h.id}
                className={cn("flex flex-wrap items-start gap-x-3 gap-y-2 rounded-2xl border p-4", h.flag ? flagSurface[h.flag] : "bg-card")}
              >
                <p className="min-w-0 flex-1 basis-60 leading-relaxed">{h.text}</p>
                <div className="flex items-center gap-2">
                  {h.flag && <FlagMarker flag={h.flag} />}
                  <EvidenceChip itemId={h.id} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {o.analysisAvailable && (
        <section aria-labelledby="explore" className="mb-10 space-y-4">
          <h2 id="explore" className="text-2xl">Explore your results</h2>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {QUICK_LINKS.map((q) => (
              <li key={q.path}>
                <Link href={`/cases/${caseId}${q.path}`} className="paper group flex h-full flex-col gap-2 p-4 transition-shadow hover:shadow-lg">
                  <span className="grid size-9 place-items-center rounded-lg bg-secondary text-secondary-foreground">
                    <q.icon aria-hidden className="size-4.5" />
                  </span>
                  <span className="font-medium">{q.title}</span>
                  <span className="text-sm text-muted-foreground">{q.body}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="docs-summary" className="mb-10 space-y-3">
        <h2 id="docs-summary" className="text-2xl">Documents</h2>
        <div className="paper flex flex-wrap items-center justify-between gap-4 p-4">
          <p className="flex items-center gap-2">
            <ClipboardList aria-hidden className="size-5 text-muted-foreground" />
            {o.documents.length} {o.documents.length === 1 ? "document" : "documents"}
            {attention > 0 && <span className="text-uncertain"> · {attention} need attention</span>}
          </p>
          <Link href={`/cases/${caseId}/documents`} className={cn(buttonVariants({ variant: "outline" }))}>View documents</Link>
        </div>
      </section>

      <Legend className="mb-10" />

      <section aria-labelledby="privacy" className="paper space-y-3 p-5 no-print">
        <h2 id="privacy" className="text-xl">Your data</h2>
        <p className="text-sm text-muted-foreground">
          You can delete this case and everything linked to it at any time. In the real product this also removes stored documents and cached outputs.
        </p>
        <Button variant="destructive" onClick={() => setConfirmDelete(true)}>
          <Trash2 aria-hidden data-icon="inline-start" /> Delete this case
        </Button>
      </section>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">Delete case {c.code}?</DialogTitle>
            <DialogDescription>This removes the case, its documents and all generated results from this prototype. This can’t be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>Keep it</Button>
            <Button
              variant="destructive"
              onClick={async () => { await api.deleteCase(caseId); router.push("/dashboard"); }}
            >
              Delete everything
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
