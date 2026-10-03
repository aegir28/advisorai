"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Comparison, ComparisonRow, Question } from "@/domain/types";
import { api } from "@/lib/api";
import { EvidenceChip } from "./evidence-chip";

/**
 * Side-by-side doctor-opinion comparison, grouped the way a person thinks:
 * what agrees, what differs, what's new, what's still unresolved.
 * It never shows a winner, a score, "Doctor A is correct", or any
 * recommendation to switch doctors.
 */

/** Friendlier chip text than a raw item ID. */
function evidenceLabel(id: string): string {
  if (id.startsWith("so_")) return "Second opinion";
  if (id.startsWith("f_")) return "Your report";
  return "Source";
}

function Side({ label, text, evidence }: { label: string; text: string; evidence: string[] }) {
  return (
    <div className="space-y-2 rounded-2xl bg-muted/60 p-4">
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      <p className="leading-relaxed">{text}</p>
      {evidence.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {evidence.map((id) => <EvidenceChip key={id} itemId={id} label={evidenceLabel(id)} describes={text} />)}
        </div>
      )}
    </div>
  );
}

const GROUPS: { title: string; hint: string; match: ComparisonRow["relationship"][] }[] = [
  { title: "What agrees", hint: "Both opinions line up here.", match: ["agreement"] },
  { title: "What differs", hint: "The opinions say different things. Both are shown.", match: ["differs", "changed"] },
  { title: "What’s new", hint: "Something the second opinion adds.", match: ["new_info"] },
  { title: "What’s still unresolved", hint: "Neither opinion settles this yet.", match: ["unresolved"] },
];

export function ComparisonView({ comparison, caseId, questions }: { comparison: Comparison; caseId: string; questions: Question[] }) {
  const [applied, setApplied] = useState(false);
  const qText = (id: string) => questions.find((q) => q.id === id)?.text ?? id;

  const apply = async () => {
    for (const a of comparison.answeredByOpinion) await api.updateQuestion(caseId, a.questionId, { status: a.status });
    setApplied(true);
  };

  return (
    <div className="space-y-14">
      {GROUPS.map((g) => {
        const rows = comparison.rows.filter((r) => g.match.includes(r.relationship));
        if (!rows.length) return null;
        return (
          <section key={g.title} aria-label={g.title} className="space-y-6">
            <div>
              <h3 className="text-2xl">{g.title}</h3>
              <p className="text-muted-foreground">{g.hint}</p>
            </div>
            <ul className="space-y-8">
              {rows.map((row) => (
                <li key={row.id} className="space-y-3">
                  <p className="font-heading text-xl text-ink">{row.topic}</p>
                  <div className="grid gap-3 md:grid-cols-2">
                    <Side label={comparison.opinionALabel} text={row.opinionA} evidence={row.evidenceA} />
                    <Side label={comparison.opinionBLabel} text={row.opinionB} evidence={row.evidenceB} />
                  </div>
                  <EvidenceChip itemId={row.id} label="Where this comes from" describes={row.topic} />
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      <section aria-label="What to ask next" className="space-y-5">
        <h3 className="text-2xl">What to ask next</h3>
        <ul className="space-y-5">
          {comparison.nextQuestions.map((q) => (
            <li key={q.text} className="border-l-2 border-primary/40 pl-4">
              <p className="text-sm text-muted-foreground">For {q.audience.toLowerCase()}</p>
              <p className="text-lg leading-snug">{q.text}</p>
            </li>
          ))}
        </ul>
      </section>

      {comparison.answeredByOpinion.length > 0 && (
        <section aria-label="Questions this may have answered" className="space-y-4 rounded-3xl bg-secondary/60 p-6">
          <h3 className="text-xl">Questions this may have answered</h3>
          <ul className="space-y-3">
            {comparison.answeredByOpinion.map((a) => (
              <li key={a.questionId}>
                <p className="font-medium">{qText(a.questionId)}</p>
                <p className="text-muted-foreground">{a.note}</p>
              </li>
            ))}
          </ul>
          <Button onClick={apply} disabled={applied} variant={applied ? "secondary" : "default"} className="rounded-xl">
            {applied ? <><Check aria-hidden data-icon="inline-start" /> Your questions are updated</> : "Update my questions"}
          </Button>
        </section>
      )}

      <p className="text-sm text-muted-foreground">
        We don’t say which doctor is right, give a score, or suggest switching doctors. Differences are here to help you ask better questions.
        Decisions stay with you and your doctors.
      </p>
    </div>
  );
}
