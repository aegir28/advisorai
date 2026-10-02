"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowRight, ChevronRight, RefreshCcw } from "lucide-react";
import { PageIntro } from "@/components/layout/page-intro";
import { EmptyState, ErrorState, LoadingState, PartialNotice } from "@/components/medical/states";
import { RunProgress } from "@/components/medical/run-progress";
import { Button, buttonVariants } from "@/components/ui/button";
import { useCase, useCrossReview, useRun } from "@/features/case/hooks";
import { api } from "@/lib/api";
import { prototype } from "@/lib/prototype";
import { invalidateQueries } from "@/lib/use-query";
import { cn } from "@/lib/utils";

const bigCta = "h-14 rounded-2xl px-8 text-base";

function HubRow({ href, title, body }: { href: string; title: string; body: string }) {
  return (
    <Link href={href} className="group flex items-center gap-4 py-5 transition-colors hover:bg-secondary/60 sm:-mx-4 sm:rounded-2xl sm:px-4">
      <div className="min-w-0 flex-1">
        <p className="font-heading text-xl text-ink">{title}</p>
        <p className="text-muted-foreground">{body}</p>
      </div>
      <ChevronRight aria-hidden className="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}

export default function AnalysisPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const c = useCase(caseId);
  const run = useRun(c.data?.runId);
  const review = useCrossReview(caseId);
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
      <EmptyState title="Your review hasn’t started" body="Add your reports first, then we’ll review your case and prepare a clear summary." action={{ label: "Add reports", href: `/cases/${caseId}/upload` }} />
    );
  }

  const r = run.data;
  const base = `/cases/${caseId}`;
  const differing = review.data?.rows.filter((x) => x.relationship === "disagreement" || x.relationship === "partial").length ?? 0;

  const retry = async () => {
    setBusy(true);
    prototype?.setNextRunOutcome(caseId, "complete");
    await api.startAnalysis(caseId);
    setBusy(false);
  };

  // ── Still working, or stopped ──
  if (r.status === "running" || r.status === "failed") {
    return (
      <>
        <PageIntro
          title={r.status === "failed" ? "We had to stop" : "Reviewing your case"}
          action={r.status === "running" && prototype ? <Button variant="ghost" size="sm" onClick={() => void prototype?.skipToResults(r.id)}>Skip ahead (prototype)</Button> : undefined}
        >
          {r.status === "failed"
            ? "Here is where things stopped, and what would help."
            : "Usually takes a few minutes. You can leave this page. We’ll keep going."}
        </PageIntro>

        {r.status === "failed" && r.failure && (
          <div role="alert" className="mb-10 space-y-4 rounded-3xl bg-urgent-soft p-6">
            <h3 className="text-xl">{r.failure.title}</h3>
            <p>{r.failure.body}</p>
            <div className="flex flex-wrap gap-3">
              <Button size="lg" className="rounded-2xl" onClick={retry} disabled={busy}><RefreshCcw aria-hidden data-icon="inline-start" /> Try again</Button>
              <Link href={`${base}/documents`} className={cn(buttonVariants({ variant: "outline", size: "lg" }), "rounded-2xl")}>Look at my reports</Link>
            </div>
          </div>
        )}

        <RunProgress run={r} />
        {r.status === "running" && prototype && <p className="mt-10 text-sm text-muted-foreground">Prototype: this takes about 20 seconds instead of a few minutes.</p>}
      </>
    );
  }

  // ── Finished: a quiet hub for the details ──
  return (
    <>
      <PageIntro title="Your analysis is ready">
        {r.status === "partial" ? "A few things couldn’t be completed. We’ve noted them wherever they matter." : "Here’s what we looked at. Open any part when you want more detail."}
      </PageIntro>

      {r.status === "partial" && (
        <div className="mb-8">
          <PartialNotice title="Some information was missing">
            <ul className="mt-1 list-disc space-y-1 pl-4">{r.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </PartialNotice>
        </div>
      )}

      <Link href={`${base}/report`} className={cn(buttonVariants({ size: "lg" }), bigCta)}>
        Read your report <ArrowRight aria-hidden data-icon="inline-end" />
      </Link>

      <section aria-labelledby="explore-h" className="mt-14">
        <h3 id="explore-h" className="mb-1 text-lg text-muted-foreground">Explore the details</h3>
        <div className="divide-y border-y">
          <HubRow href={`${base}/analysis/timeline`} title="Your medical timeline" body="Your history in order, with gaps marked." />
          <HubRow href={`${base}/analysis/perspectives`} title="Specialist perspectives" body="We looked at your case from several medical perspectives." />
          <HubRow href={`${base}/analysis/evidence`} title="Supporting evidence" body="How we checked what we found." />
          <HubRow
            href={`${base}/analysis/differences`}
            title="Where information differs"
            body={differing > 0 ? `${differing} ${differing === 1 ? "area" : "areas"} where the information doesn’t fully agree.` : "Where views agree, and where they don’t."}
          />
          <HubRow href={`${base}/analysis/summary`} title="How we pulled it together" body="The combined view your report is written from." />
        </div>
      </section>

      <details className="no-print mt-12 text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">What we did</summary>
        <div className="mt-6"><RunProgress run={r} /></div>
      </details>
    </>
  );
}
