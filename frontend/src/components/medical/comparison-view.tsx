"use client";

import { useState } from "react";
import { ArrowRightLeft, Check, CircleDashed, FilePlus2, Split, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Comparison, ComparisonRelationship, Question } from "@/domain/types";
import { api } from "@/lib/api";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";

/**
 * Side-by-side doctor-opinion comparison. It explains the difference and the
 * evidence behind each view. It never shows a winner, a score, "Doctor A is
 * correct", or any recommendation to switch doctors.
 */

const relStyle: Record<ComparisonRelationship, { icon: LucideIcon; cls: string }> = {
  agreement: { icon: Check, cls: "bg-fact-soft text-fact border-fact/25" },
  differs: { icon: Split, cls: "bg-disagree-soft text-disagree border-disagree/30" },
  new_info: { icon: FilePlus2, cls: "bg-evidence-soft text-evidence border-evidence/25" },
  changed: { icon: ArrowRightLeft, cls: "bg-interp-soft text-interp border-interp/25" },
  unresolved: { icon: CircleDashed, cls: "bg-missing-soft text-missing border-missing/50 border-dashed" },
};

/** Friendlier chip text than a raw item ID. */
function evidenceLabel(id: string): string {
  if (id.startsWith("so_")) return "Second opinion";
  if (id.startsWith("f_")) return "Your record";
  return "Source";
}

function Side({ label, text, evidence }: { label: string; text: string; evidence: string[] }) {
  return (
    <div className="space-y-2 rounded-xl bg-muted/50 p-3.5">
      <p className="eyebrow">{label}</p>
      <p className="leading-relaxed">{text}</p>
      {evidence.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {evidence.map((id) => <EvidenceChip key={id} itemId={id} label={evidenceLabel(id)} />)}
        </div>
      )}
    </div>
  );
}

export function ComparisonView({ comparison, caseId, questions }: { comparison: Comparison; caseId: string; questions: Question[] }) {
  const [applied, setApplied] = useState(false);
  const qText = (id: string) => questions.find((q) => q.id === id)?.text ?? id;

  const apply = async () => {
    for (const a of comparison.answeredByOpinion) await api.updateQuestion(caseId, a.questionId, { status: a.status });
    setApplied(true);
  };

  return (
    <div className="space-y-10">
      <ul className="space-y-4">
        {comparison.rows.map((row) => {
          const { icon: Icon, cls } = relStyle[row.relationship];
          return (
            <li key={row.id} className="paper space-y-4 p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-lg">{row.topic}</h3>
                <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", cls)}>
                  <Icon aria-hidden className="size-3.5" /> {tk(`cmp.${row.relationship}`)}
                </span>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Side label={comparison.opinionALabel} text={row.opinionA} evidence={row.evidenceA} />
                <Side label={comparison.opinionBLabel} text={row.opinionB} evidence={row.evidenceB} />
              </div>
              <EvidenceChip itemId={row.id} label="Trace this comparison" />
            </li>
          );
        })}
      </ul>

      <section aria-labelledby="next-q" className="space-y-3">
        <h2 id="next-q" className="text-2xl">What still needs clarifying</h2>
        <ul className="space-y-3">
          {comparison.nextQuestions.map((q) => (
            <li key={q.text} className="paper flex flex-wrap items-start justify-between gap-3 p-4">
              <div className="min-w-0 flex-1 basis-64 space-y-1">
                <p className="eyebrow">Ask: {q.audience}</p>
                <p className="text-lg leading-snug">{q.text}</p>
              </div>
              {q.itemIds.map((id) => <EvidenceChip key={id} itemId={id} />)}
            </li>
          ))}
        </ul>
      </section>

      {comparison.answeredByOpinion.length > 0 && (
        <section aria-labelledby="answered" className="paper space-y-4 p-5">
          <h2 id="answered" className="text-xl">Questions this second opinion may have answered</h2>
          <ul className="space-y-3">
            {comparison.answeredByOpinion.map((a) => (
              <li key={a.questionId} className="space-y-0.5 text-sm">
                <p className="font-medium">{qText(a.questionId)}</p>
                <p className="text-muted-foreground">{a.note}</p>
              </li>
            ))}
          </ul>
          <Button onClick={apply} disabled={applied} variant={applied ? "secondary" : "default"}>
            {applied ? <><Check aria-hidden data-icon="inline-start" /> Tracker updated</> : "Update my question tracker"}
          </Button>
        </section>
      )}

      <aside className="rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
        <p className="mb-1 font-medium text-foreground">What this page never does</p>
        <p>
          It doesn’t say which doctor is right, give a score or a winner, suggest switching doctors, or give any treatment instruction.
          Differences are there to help you ask better questions. Decisions stay with you and your doctors.
        </p>
      </aside>
    </div>
  );
}
