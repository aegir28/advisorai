import { ArrowRightLeft, CircleDashed, CircleHelp, Flag, Pill, Plus, Split, Check, type LucideIcon } from "lucide-react";
import type { CellStance, CrossReviewData, MatrixRow, Relationship } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";

/**
 * Cross-specialist review. Differences are shown with each side's reasoning.
 * There is no majority count, no winner and no correctness colouring.
 */

const relStyle: Record<Relationship, { icon: LucideIcon; cls: string }> = {
  agreement: { icon: Check, cls: "bg-fact-soft text-fact border-fact/25" },
  partial: { icon: ArrowRightLeft, cls: "bg-fact-soft text-fact border-fact/25" },
  disagreement: { icon: Split, cls: "bg-disagree-soft text-disagree border-disagree/30" },
  missing_info: { icon: CircleDashed, cls: "bg-missing-soft text-missing border-missing/50 border-dashed" },
  medication_conflict: { icon: Pill, cls: "bg-uncertain-soft text-uncertain border-uncertain/30" },
  additional_context: { icon: Plus, cls: "bg-muted text-muted-foreground border-border" },
};

const stanceStyle: Record<CellStance, { icon: LucideIcon; cls: string }> = {
  supports: { icon: Check, cls: "bg-fact-soft text-fact border-fact/20" },
  needs_context: { icon: CircleHelp, cls: "bg-uncertain-soft text-uncertain border-uncertain/30" },
  differs: { icon: Split, cls: "bg-disagree-soft text-disagree border-disagree/30" },
  flags_issue: { icon: Flag, cls: "bg-missing-soft text-missing border-missing/50 border-dashed" },
  not_assessed: { icon: CircleDashed, cls: "bg-transparent text-muted-foreground/70 border-border border-dashed" },
};

export function RelationshipBadge({ relationship }: { relationship: Relationship }) {
  const { icon: Icon, cls } = relStyle[relationship];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", cls)}>
      <Icon aria-hidden className="size-3.5" />
      {tk(`rel.${relationship}`)}
    </span>
  );
}

function StanceChip({ stance }: { stance: CellStance }) {
  const { icon: Icon, cls } = stanceStyle[stance];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium", cls)}>
      <Icon aria-hidden className="size-3" />
      {tk(`cell.${stance}`)}
    </span>
  );
}

function Row({ row, specialists }: { row: MatrixRow; specialists: CrossReviewData["specialists"] }) {
  const nameOf = (id: string) => specialists.find((s) => s.id === id)?.name ?? id;
  return (
    <li className={cn("paper space-y-4 p-4 sm:p-5", row.relationship === "disagreement" && "border-disagree/30")}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="max-w-xl text-lg leading-snug">{row.topic}</h3>
        <RelationshipBadge relationship={row.relationship} />
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        {specialists.map((s) => (
          <div key={s.id} className="space-y-1">
            <dt className="text-xs text-muted-foreground">{s.name}</dt>
            <dd><StanceChip stance={row.cells[s.id] ?? "not_assessed"} /></dd>
          </div>
        ))}
      </dl>

      <p className="text-sm leading-relaxed">{row.summary}</p>

      <details className="group rounded-xl bg-muted/50 px-3 py-2">
        <summary className="cursor-pointer list-none text-sm font-medium">
          <span className="group-open:hidden">See each perspective’s reasoning</span>
          <span className="hidden group-open:inline">Hide reasoning</span>
        </summary>
        <ul className="mt-3 space-y-2 text-sm">
          {row.perspectives.map((p) => (
            <li key={p.specialist} className="flex gap-2">
              <span className="w-40 shrink-0 font-medium">{nameOf(p.specialist)}</span>
              <span className="text-muted-foreground">{p.reasoning}</span>
            </li>
          ))}
        </ul>
      </details>

      <div className="flex flex-wrap items-center gap-2">
        <EvidenceChip itemId={row.id} label="Trace this row" describes={row.topic} />
      </div>
    </li>
  );
}

export function DisagreementMatrix({ data }: { data: CrossReviewData }) {
  return (
    <ul className="space-y-4">
      {data.rows.map((r) => <Row key={r.id} row={r} specialists={data.specialists} />)}
    </ul>
  );
}
