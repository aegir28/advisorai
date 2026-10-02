"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowRight, Upload } from "lucide-react";
import { EvidenceChip } from "@/components/medical/evidence-chip";
import { FlagMarker } from "@/components/medical/markers";
import { ErrorState, LoadingState, PartialNotice } from "@/components/medical/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { ReportItem } from "@/domain/types";
import { useCaseOverview, useQuestions, useReport, useRun } from "@/features/case/hooks";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const bigCta = "h-14 rounded-2xl px-8 text-base";

/** One quiet block: a heading with a count, a few sentences, nothing else. */
function Block({ title, count, children, empty }: { title: string; count: string; children: React.ReactNode; empty?: boolean }) {
  return (
    <section className="space-y-4" aria-label={title}>
      <div>
        <h2 className="text-2xl">{title}</h2>
        {!empty && <p className="text-muted-foreground">{count}</p>}
      </div>
      {children}
    </section>
  );
}

function Sentence({ item }: { item: ReportItem }) {
  return (
    <li className="space-y-1.5">
      <p className="text-lg leading-relaxed">{item.text}</p>
      <div className="flex flex-wrap items-center gap-2">
        {item.flag && <FlagMarker flag={item.flag} />}
        {item.evidenceIds.map((id) => <EvidenceChip key={id} itemId={id} />)}
      </div>
    </li>
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export default function CaseOverviewPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const router = useRouter();
  const overview = useCaseOverview(caseId);
  const run = useRun(overview.data?.summary.runId);
  const report = useReport(caseId);
  const questions = useQuestions(caseId);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (overview.status === "loading") return <LoadingState rows={2} />;
  if (overview.status === "error") return <ErrorState onRetry={overview.reload} />;
  const o = overview.data;
  if (!o) return null;
  const { summary: c } = o;

  const section = (n: number) => report.data?.sections.find((s) => s.number === n)?.items.filter((i) => i.kind !== "template") ?? [];
  const found = section(2);
  const unclear = [...section(9), ...section(10)];
  const asked = questions.data ?? [];
  const priority = asked.filter((q) => q.priority === 1);

  return (
    <div className="space-y-14">
      {(c.status === "draft" || c.status === "awaiting_upload") && (
        <section className="space-y-4">
          <h2 className="text-2xl">Next, add your reports</h2>
          <p className="text-lg text-muted-foreground">We need at least one report before we can review your case.</p>
          <Link href={`/cases/${caseId}/upload`} className={cn(buttonVariants({ size: "lg" }), bigCta)}>
            <Upload aria-hidden data-icon="inline-start" /> Add reports
          </Link>
        </section>
      )}

      {c.status === "processing" && (
        <section className="space-y-4">
          <h2 className="text-2xl">We’re reviewing your case</h2>
          <p className="text-lg text-muted-foreground">You can leave this page. We’ll keep going.</p>
          <Link href={`/cases/${caseId}/analysis`} className={cn(buttonVariants({ size: "lg" }), bigCta)}>
            See progress <ArrowRight aria-hidden data-icon="inline-end" />
          </Link>
        </section>
      )}

      {c.status === "failed" && (
        <section role="alert" className="space-y-4 rounded-3xl bg-urgent-soft p-6">
          <h2 className="text-2xl">We couldn’t finish your review</h2>
          <p className="text-lg">One of your reports was too hard to read safely. Nothing was lost. A clearer copy would help.</p>
          <Link href={`/cases/${caseId}/analysis`} className={cn(buttonVariants({ size: "lg" }), bigCta)}>See what happened</Link>
        </section>
      )}

      {o.analysisAvailable && (
        <>
          {c.status === "partial" && (
            <PartialNotice title="Some information was missing, so parts of this summary are less complete.">
              {run.data?.warnings.length ? (
                <ul className="mt-1 list-disc space-y-1 pl-4">{run.data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
              ) : null}
            </PartialNotice>
          )}

          <Block title="Your case" count="" empty>
            {report.status === "loading" ? <LoadingState rows={1} /> : (
              <ul className="space-y-4">{section(1).map((i) => <Sentence key={i.id} item={i} />)}</ul>
            )}
          </Block>

          <Block title="What we found" count={plural(found.length, "important finding", "important findings")} empty={!found.length}>
            <ul className="space-y-5">{found.slice(0, 3).map((i) => <Sentence key={i.id} item={i} />)}</ul>
          </Block>

          <Block title="What is still unclear" count={plural(unclear.length, "thing needs", "things need") + " clarification"} empty={!unclear.length}>
            <ul className="space-y-5">{unclear.slice(0, 3).map((i) => <Sentence key={i.id} item={i} />)}</ul>
          </Block>

          <Block title="Questions worth asking" count={plural(asked.length, "question", "questions") + (priority.length ? `, ${priority.length} to start with` : "")} empty={!asked.length}>
            <ul className="space-y-3">
              {priority.slice(0, 3).map((q) => (
                <li key={q.id} className="border-l-2 border-primary/40 pl-4 text-lg leading-relaxed">{q.text}</li>
              ))}
            </ul>
            <Link href={`/cases/${caseId}/questions`} className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline">
              See all questions <ArrowRight aria-hidden className="size-4" />
            </Link>
          </Block>

          <div className="space-y-4 border-t pt-10">
            <Link href={`/cases/${caseId}/analysis`} className={cn(buttonVariants({ size: "lg" }), bigCta)}>
              View full analysis <ArrowRight aria-hidden data-icon="inline-end" />
            </Link>
            <p className="text-muted-foreground">
              Or <Link href={`/cases/${caseId}/report`} className="font-medium text-primary underline underline-offset-4">read your full report</Link>.
            </p>
          </div>
        </>
      )}

      <details className="no-print text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">More about this case</summary>
        <div className="mt-4 space-y-3">
          <p>
            <Link href={`/cases/${caseId}/documents`} className="text-primary underline underline-offset-4">Your reports ({o.documents.length})</Link>
          </p>
          <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)}>Delete this case</Button>
        </div>
      </details>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">Delete this case?</DialogTitle>
            <DialogDescription>This removes the case, its reports and everything we prepared from this prototype. It can’t be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>Keep it</Button>
            <Button variant="destructive" onClick={async () => { await api.deleteCase(caseId); router.push("/cases"); }}>Delete everything</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
