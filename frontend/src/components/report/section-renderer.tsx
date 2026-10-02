import type { FC } from "react";
import Link from "next/link";
import type { ReportItem, ReportSection, ReportSectionType } from "@/domain/types";
import { formatDate, formatMonth } from "@/lib/format";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "@/components/medical/evidence-chip";
import { ConfidenceBadge, FlagMarker, KindTag, flagSurface, kindAccent } from "@/components/medical/markers";
import type { Confidence } from "@/domain/types";

/**
 * Renders any report section from JSON. The report layout is data-driven:
 * a new section type needs one renderer here and no new page. Unknown types
 * fall back to a plain list, so the page never breaks on new backend output.
 *
 * Rule: every sentence carries an item ID and a "Source" chip. Only fixed
 * template text (headings, disclaimers, "nothing found" notes) is untraced.
 */

function Sentence({ item, caseId }: { item: ReportItem; caseId?: string }) {
  void caseId;
  if (item.kind === "template") {
    return <p className="rounded-xl bg-muted/60 px-4 py-3 text-sm leading-relaxed text-muted-foreground">{item.text}</p>;
  }
  return (
    <div
      className={cn(
        "space-y-2 rounded-xl border border-l-4 p-4",
        item.flag ? flagSurface[item.flag] : "bg-card",
        kindAccent(item.kind),
      )}
    >
      <p className="text-[1.05rem] leading-relaxed">
        {item.text}
        {item.id && <span className="print-only ml-1 text-xs text-muted-foreground">[{item.id}]</span>}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <KindTag kind={item.kind} />
        {item.flag && <FlagMarker flag={item.flag} />}
        {item.evidenceIds.map((id) => <EvidenceChip key={id} itemId={id} className="ml-auto first:ml-auto" />)}
      </div>
    </div>
  );
}

const ListSection: FC<{ section: ReportSection }> = ({ section }) => (
  <ul className="space-y-3">
    {section.items.map((it, i) => <li key={it.id ?? i}><Sentence item={it} /></li>)}
  </ul>
);

const MedicinesSection: FC<{ section: ReportSection }> = ({ section }) => (
  <div className="space-y-3">
    <ul className="divide-y rounded-xl border bg-card">
      {section.items.map((m) => (
        <li key={m.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3">
          <div className="min-w-0">
            <p className="font-medium">{m.text}</p>
            <p className="text-sm text-muted-foreground">{m.meta?.dose}</p>
          </div>
          {m.evidenceIds.map((id) => <EvidenceChip key={id} itemId={id} />)}
        </li>
      ))}
    </ul>
    <p className="text-sm text-muted-foreground">This is only what your records list. Please don’t start, stop or change any medicine on your own. Your prescriber decides.</p>
  </div>
);

const TimelineSection: FC<{ section: ReportSection }> = ({ section }) => (
  <ol className="space-y-2.5">
    {section.items.map((e) => {
      const isGap = e.meta?.gap === "true";
      return (
        <li key={e.id} className={cn("grid gap-x-4 gap-y-1.5 rounded-xl border p-3.5 sm:grid-cols-[7.5rem_1fr]", e.flag ? flagSurface[e.flag] : "bg-card")}>
          <p className="text-sm font-medium text-muted-foreground">
            {isGap ? "Possible gap" : e.meta?.precision === "day" ? formatDate(e.meta.date) : e.meta?.date ? formatMonth(e.meta.date) : ""}
          </p>
          <div className="space-y-2">
            <p>{e.text}</p>
            <div className="flex flex-wrap items-center gap-2">
              {e.flag && <FlagMarker flag={e.flag} label={isGap ? undefined : "Two versions in your records"} />}
              {e.evidenceIds.map((id) => <EvidenceChip key={id} itemId={id} className="ml-auto" />)}
            </div>
          </div>
        </li>
      );
    })}
  </ol>
);

const PerspectivesSection: FC<{ section: ReportSection }> = ({ section }) => {
  const groups = new Map<string, ReportItem[]>();
  for (const it of section.items) {
    const key = it.meta?.specialist ?? "Perspective";
    groups.set(key, [...(groups.get(key) ?? []), it]);
  }
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">Each specialist view is kept separate. “Perspective” means a reasoned view to discuss, not a verdict.</p>
      {[...groups.entries()].map(([name, items]) => (
        <div key={name} className="space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg">{name}</h3>
            {items[0]?.meta?.confidence && <ConfidenceBadge confidence={items[0].meta.confidence as Confidence} />}
          </div>
          {items.map((it, i) => <Sentence key={it.id ?? i} item={it} />)}
        </div>
      ))}
    </div>
  );
};

const DisagreementsSection: FC<{ section: ReportSection }> = ({ section }) => (
  <div className="space-y-3">
    <p className="text-sm text-muted-foreground">Where perspectives differ we show both. We don’t say which is right.</p>
    <ul className="space-y-3">{section.items.map((it, i) => <li key={it.id ?? i}><Sentence item={it} /></li>)}</ul>
  </div>
);

const QuestionsSection: FC<{ section: ReportSection }> = ({ section }) => (
  <div className="space-y-3">
    <ol className="space-y-2.5">
      {section.items.map((q, i) => (
        <li key={q.id} className="flex gap-3 rounded-xl border bg-card p-4">
          <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-full bg-secondary font-heading text-sm text-secondary-foreground">{i + 1}</span>
          <div className="min-w-0 flex-1 space-y-2">
            <p className="text-[1.05rem] leading-snug">{q.text}</p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="rounded-full bg-primary px-2 py-0.5 font-medium text-primary-foreground">P{q.meta?.priority}</span>
              <span>{q.meta?.category}</span>
              {q.evidenceIds.map((id) => <EvidenceChip key={id} itemId={id} label="Why this question" className="ml-auto" />)}
            </div>
          </div>
        </li>
      ))}
    </ol>
  </div>
);

const ReferencesSection: FC<{ section: ReportSection }> = ({ section }) => (
  <ul className="space-y-2.5">
    {section.items.map((r) => (
      <li key={r.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border bg-card p-4 text-sm">
        <p className="min-w-0 flex-1 basis-60">{r.text}</p>
        {r.evidenceIds.map((id) => <EvidenceChip key={id} itemId={id} />)}
      </li>
    ))}
    <li className="text-xs text-muted-foreground">Prototype note: reference summaries here are synthetic placeholders, not real guidelines.</li>
  </ul>
);

const DisclaimerSection: FC<{ section: ReportSection }> = ({ section }) => (
  <div className="space-y-3 rounded-xl border-2 border-primary/30 bg-accent/40 p-5">
    {section.items.map((it, i) => <p key={i} className="leading-relaxed">{it.text}</p>)}
    <p className="text-sm text-muted-foreground">If you have urgent symptoms, call 112 or 108, or go to the nearest emergency department.</p>
  </div>
);

const RENDERERS: Record<ReportSectionType, FC<{ section: ReportSection }>> = {
  prose: ListSection,
  bullets: ListSection,
  agreements: ListSection,
  medicines: MedicinesSection,
  timeline: TimelineSection,
  perspectives: PerspectivesSection,
  disagreements: DisagreementsSection,
  questions: QuestionsSection,
  references: ReferencesSection,
  disclaimer: DisclaimerSection,
};

export function SectionRenderer({ section, caseId }: { section: ReportSection; caseId: string }) {
  // Unknown section types (e.g. from a newer backend) degrade to a plain list.
  const Renderer = RENDERERS[section.type] ?? ListSection;
  const titleId = `report-s${section.number}`;
  return (
    <section id={`s${section.number}`} aria-labelledby={titleId} className="report-section scroll-mt-28 space-y-4">
      <header className="flex items-baseline gap-3 border-b pb-2">
        <span aria-hidden className="font-heading text-2xl text-muted-foreground/60">{section.number}</span>
        <h2 id={titleId} className="text-2xl">{tk(`report.s${section.number}`)}</h2>
      </header>
      <Renderer section={section} />
      {section.type === "questions" && (
        <Link href={`/cases/${caseId}/questions`} data-no-print className="no-print inline-block text-sm font-medium text-primary underline underline-offset-4">
          Open the question tracker
        </Link>
      )}
    </section>
  );
}
