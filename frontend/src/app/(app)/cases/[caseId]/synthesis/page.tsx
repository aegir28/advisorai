"use client";

import { useParams } from "next/navigation";
import { Bot, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ResultsGate } from "@/components/case/results-gate";
import { EvidenceChip } from "@/components/medical/evidence-chip";
import { Legend } from "@/components/medical/legend";
import { ConfidenceBadge, FlagMarker, KindTag, flagSurface, kindAccent } from "@/components/medical/markers";
import { useSynthesis } from "@/features/case/hooks";
import type { SynthesisItem } from "@/domain/types";
import { cn } from "@/lib/utils";

const GROUPS: { title: string; groups: SynthesisItem["group"][]; hint: string }[] = [
  { title: "What your records state", groups: ["fact", "proposal"], hint: "Directly from your documents." },
  { title: "Where perspectives agree", groups: ["agreement"], hint: "Kept for transparency; agreement is not proof." },
  { title: "Where perspectives differ", groups: ["disagreement"], hint: "Shown as perspectives to discuss, not decided." },
  { title: "Missing information", groups: ["missing"], hint: "Ranked by how much it could matter." },
  { title: "High-impact uncertainties", groups: ["uncertainty"], hint: "What the records cannot settle." },
  { title: "Medicine points to review", groups: ["medication"], hint: "Worth raising with your prescriber." },
  { title: "Reasoned interpretations", groups: ["interpretation"], hint: "AI interpretation, not facts from your records." },
  { title: "Areas needing clarification", groups: ["clarification"], hint: "Seeds for your questions." },
];

const impactRank = { high: 0, medium: 1, low: 2 } as const;

function Item({ item }: { item: SynthesisItem }) {
  return (
    <li className={cn("space-y-2.5 rounded-xl border border-l-4 p-4", item.flag ? flagSurface[item.flag] : "bg-card", kindAccent(item.kind))}>
      <p className="leading-relaxed">{item.text}</p>
      <div className="flex flex-wrap items-center gap-2">
        <KindTag kind={item.kind} />
        {item.flag && <FlagMarker flag={item.flag} />}
        <ConfidenceBadge confidence={item.confidence} />
        <EvidenceChip itemId={item.id} className="ml-auto" />
      </div>
    </li>
  );
}

export default function SynthesisPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const q = useSynthesis(caseId);
  return (
    <>
      <PageHeader
        eyebrow="AI summary"
        title="The reviewer’s combined picture"
        description="This is the internal summary the patient report is written from. It keeps genuine disagreements and labels uncertainty."
      />
      <ResultsGate query={q} caseId={caseId}>
        {(s) => (
          <div className="space-y-8">
            <section className="paper space-y-3 p-5" aria-labelledby="rev-h">
              <h2 id="rev-h" className="flex items-center gap-2 text-xl"><Bot aria-hidden className="size-5 text-primary" /> {s.reviewer.label}</h2>
              <p className="text-sm text-muted-foreground">
                This is an AI synthesis and verification layer. <strong className="font-medium text-foreground">It is not a human doctor</strong>, does not
                make treatment decisions, and never overrides your own doctors.
              </p>
              <p className="flex items-center gap-1.5 text-sm"><TrendingUp aria-hidden className="size-4 text-muted-foreground" /> Reasoning tier {s.reviewer.tier}{s.reviewer.escalated ? " (escalated)" : ""}</p>
              {s.reviewer.escalationReason && <p className={cn("rounded-xl border p-3 text-sm", flagSurface.uncertain)}>{s.reviewer.escalationReason}</p>}
            </section>

            <Legend />

            {GROUPS.map((g) => {
              const items = s.items
                .filter((i) => g.groups.includes(i.group))
                .sort((a, b) => impactRank[a.impact ?? "low"] - impactRank[b.impact ?? "low"]);
              if (!items.length) return null;
              return (
                <section key={g.title} className="space-y-3" aria-label={g.title}>
                  <div>
                    <h2 className="text-xl">{g.title}</h2>
                    <p className="text-sm text-muted-foreground">{g.hint}</p>
                  </div>
                  <ul className="space-y-3">{items.map((i) => <Item key={i.id} item={i} />)}</ul>
                </section>
              );
            })}

            <section className="paper space-y-3 p-5" aria-labelledby="rubric-h">
              <h2 id="rubric-h" className="text-xl">How the reviewer weighs things</h2>
              <p className="text-sm text-muted-foreground">A weighted rubric, not a vote. The number of perspectives agreeing is only ever a tie-break.</p>
              <table className="w-full text-sm">
                <caption className="sr-only">Reviewer decision rubric</caption>
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th scope="col" className="py-2 font-medium">Factor</th>
                    <th scope="col" className="py-2 text-right font-medium">Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {s.rubric.map((r) => (
                    <tr key={r.factor} className="border-b last:border-0">
                      <td className="py-2">{r.factor}</td>
                      <td className="py-2 text-right text-muted-foreground">{r.weight}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        )}
      </ResultsGate>
    </>
  );
}
