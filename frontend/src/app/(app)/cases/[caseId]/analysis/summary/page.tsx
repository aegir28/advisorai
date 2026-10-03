"use client";

import { useParams } from "next/navigation";
import { ResultsGate } from "@/components/case/results-gate";
import { BackLink } from "@/components/layout/back-link";
import { PageIntro } from "@/components/layout/page-intro";
import { EvidenceChip } from "@/components/medical/evidence-chip";
import { FlagMarker, KindTag, flagSurface } from "@/components/medical/markers";
import { useSynthesis } from "@/features/case/hooks";
import type { SynthesisItem } from "@/domain/types";
import { cn } from "@/lib/utils";

const GROUPS: { title: string; groups: SynthesisItem["group"][] }[] = [
  { title: "What your reports state", groups: ["fact", "proposal"] },
  { title: "Where views agree", groups: ["agreement"] },
  { title: "Where views differ", groups: ["disagreement"] },
  { title: "What we couldn’t find", groups: ["missing"] },
  { title: "What is uncertain", groups: ["uncertainty"] },
  { title: "Medicines to review", groups: ["medication"] },
  { title: "Our reading of it", groups: ["interpretation"] },
  { title: "Worth clarifying", groups: ["clarification"] },
];

const impactRank = { high: 0, medium: 1, low: 2 } as const;

function Item({ item }: { item: SynthesisItem }) {
  return (
    <li className={cn("space-y-1.5", item.flag && cn("rounded-2xl border p-4", flagSurface[item.flag]))}>
      <p className="text-[1.05rem] leading-relaxed">{item.text}</p>
      <div className="flex flex-wrap items-center gap-2">
        <KindTag kind={item.kind} plain />
        {item.flag && <FlagMarker flag={item.flag} />}
        <EvidenceChip itemId={item.id} describes={item.text} />
      </div>
    </li>
  );
}

export default function SummaryPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = useSynthesis(caseId);
  return (
    <>
      <BackLink href={`/cases/${caseId}/analysis`}>Analysis</BackLink>
      <PageIntro title="How we pulled it together">
        This is the combined view your report is written from. It keeps genuine disagreements and says plainly when something is uncertain.
      </PageIntro>
      <ResultsGate query={q} caseId={caseId}>
        {(s) => (
          <div className="space-y-12">
            <p className="text-sm text-muted-foreground">
              Prepared by an AI reviewer. <strong className="font-medium text-foreground">It is not a doctor</strong> and doesn’t make treatment decisions.
            </p>

            {GROUPS.map((g) => {
              const items = s.items
                .filter((i) => g.groups.includes(i.group))
                .sort((a, b) => impactRank[a.impact ?? "low"] - impactRank[b.impact ?? "low"]);
              if (!items.length) return null;
              return (
                <section key={g.title} aria-label={g.title} className="space-y-5">
                  <h3 className="text-2xl">{g.title}</h3>
                  <ul className="space-y-5">{items.map((i) => <Item key={i.id} item={i} />)}</ul>
                </section>
              );
            })}

            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">How the reviewer weighs things</summary>
              <div className="mt-4 space-y-3 text-muted-foreground">
                <p>
                  A weighted rubric, not a vote. How many perspectives agree is only ever used to break a tie.
                  {s.reviewer.escalated && ` ${s.reviewer.escalationReason ?? ""}`}
                </p>
                <ul className="space-y-1">
                  {s.rubric.map((r) => <li key={r.factor}>{r.factor} — <span className="text-foreground">{r.weight}</span></li>)}
                </ul>
              </div>
            </details>
          </div>
        )}
      </ResultsGate>
    </>
  );
}
