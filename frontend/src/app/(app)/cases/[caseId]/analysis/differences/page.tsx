"use client";

import { useParams } from "next/navigation";
import { ResultsGate } from "@/components/case/results-gate";
import { BackLink } from "@/components/layout/back-link";
import { PageIntro } from "@/components/layout/page-intro";
import { DisagreementMatrix } from "@/components/medical/disagreement-matrix";
import { EvidenceChip } from "@/components/medical/evidence-chip";
import { FlagMarker, flagSurface } from "@/components/medical/markers";
import { useCrossReview } from "@/features/case/hooks";
import type { Flag, MatrixRow } from "@/domain/types";
import { cn } from "@/lib/utils";

/** One topic. The "See what differs" disclosure reveals each view's reasoning. */
function DifferenceCard({ row, flag, nameOf }: { row: MatrixRow; flag?: Flag; nameOf: (id: string) => string }) {
  return (
    <li className={cn("space-y-3 rounded-3xl border p-5", flag ? flagSurface[flag] : "bg-card")}>
      {flag && <FlagMarker flag={flag} />}
      <h3 className="text-xl leading-snug">{row.topic}</h3>
      <p className="leading-relaxed">{row.summary}</p>
      <details className="group">
        <summary className="cursor-pointer list-none text-sm font-medium text-primary underline-offset-4 hover:underline">
          <span className="group-open:hidden">See what differs</span>
          <span className="hidden group-open:inline">Hide</span>
        </summary>
        <ul className="mt-4 space-y-4">
          {row.perspectives.map((p) => (
            <li key={p.specialist}>
              <p className="text-sm font-medium">{nameOf(p.specialist)}</p>
              <p className="text-muted-foreground">{p.reasoning}</p>
            </li>
          ))}
          <li><EvidenceChip itemId={row.id} label="Where this comes from" describes={row.topic} /></li>
        </ul>
      </details>
    </li>
  );
}

export default function DifferencesPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = useCrossReview(caseId);
  return (
    <>
      <BackLink href={`/cases/${caseId}/analysis`}>Analysis</BackLink>
      <PageIntro title="Where information differs">
        Wherever the available information doesn’t fully agree, we show every view, with its reasoning. We don’t pick a side or count votes.
      </PageIntro>
      <ResultsGate query={q} caseId={caseId}>
        {(data) => {
          const differ = data.rows.filter((r) => r.relationship === "disagreement" || r.relationship === "partial");
          const gaps = data.rows.filter((r) => r.relationship === "missing_info");
          const worth = data.rows.filter((r) => r.relationship === "medication_conflict" || r.relationship === "additional_context");
          const agree = data.rows.filter((r) => r.relationship === "agreement");
          const nameOf = (id: string) => data.specialists.find((s) => s.id === id)?.name ?? id.replace(/_/g, " ");
          return (
            <div className="space-y-12">
              <section aria-label="Where information differs" className="space-y-5">
                <p className="text-lg">
                  {differ.length === 0
                    ? "We didn’t find areas where the perspectives disagree."
                    : differ.length === 1
                      ? "We found one area where the available information does not fully agree."
                      : `We found ${differ.length} areas where the available information does not fully agree.`}
                </p>
                <ul className="space-y-4">
                  {differ.map((r) => <DifferenceCard key={r.id} row={r} nameOf={nameOf} flag={r.relationship === "disagreement" ? "disagreement" : undefined} />)}
                </ul>
              </section>

              {gaps.length > 0 && (
                <section aria-label="Things we couldn’t find" className="space-y-4">
                  <h3 className="text-2xl">Things we couldn’t find</h3>
                  <ul className="space-y-4">{gaps.map((r) => <DifferenceCard key={r.id} row={r} nameOf={nameOf} flag="missing" />)}</ul>
                </section>
              )}

              {worth.length > 0 && (
                <section aria-label="Worth raising with your doctor" className="space-y-4">
                  <h3 className="text-2xl">Worth raising with your doctor</h3>
                  <ul className="space-y-4">{worth.map((r) => <DifferenceCard key={r.id} row={r} nameOf={nameOf} />)}</ul>
                </section>
              )}

              {agree.length > 0 && (
                <details className="group">
                  <summary className="cursor-pointer list-none text-2xl font-heading text-ink">
                    Where views agree <span className="text-muted-foreground">· {agree.length}</span>
                  </summary>
                  <ul className="mt-5 space-y-4">{agree.map((r) => <DifferenceCard key={r.id} row={r} nameOf={nameOf} />)}</ul>
                </details>
              )}

              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Compare every perspective side by side</summary>
                <div className="mt-6"><DisagreementMatrix data={data} /></div>
              </details>
            </div>
          );
        }}
      </ResultsGate>
    </>
  );
}
