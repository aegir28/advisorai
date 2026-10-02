import { TriangleAlert } from "lucide-react";
import type { Finding, SpecialistReport } from "@/domain/types";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";
import { ConfidenceBadge, FlagMarker, ImportanceLabel, KindTag, flagSurface, kindAccent } from "./markers";

/** One finding from a specialist. Always shows whether it is fact, interpretation or reference. */
export function FindingCard({ finding }: { finding: Finding }) {
  return (
    <li className={cn("space-y-2 rounded-xl border border-l-4 bg-card p-3.5", kindAccent(finding.kind))}>
      <p className="leading-relaxed">{finding.statement}</p>
      <div className="flex flex-wrap items-center gap-2">
        <KindTag kind={finding.kind} />
        <ImportanceLabel importance={finding.importance} />
        <EvidenceChip itemId={finding.id} className="ml-auto" />
      </div>
    </li>
  );
}

/** A specialist's full perspective, kept separate from the others. */
export function PerspectiveCard({ report }: { report: SpecialistReport }) {
  const incomplete = report.status !== "complete";
  return (
    <article className={cn("paper space-y-5 p-5", incomplete && "border-dashed border-uncertain/50")} aria-labelledby={`p-${report.id}`}>
      <header className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id={`p-${report.id}`} className="text-xl">{report.name}</h3>
          <span className="text-xs text-muted-foreground">v{report.version} · tier {report.tier} · {report.priority}</span>
        </div>
        <p className="text-sm text-muted-foreground">Why included: {report.routingReason}</p>
        <div className="flex flex-wrap items-center gap-2">
          <ConfidenceBadge confidence={report.confidence.overall} />
          <span className="text-sm text-muted-foreground">{report.confidence.reason}</span>
        </div>
      </header>

      {incomplete && (
        <div role="note" className="flex gap-3 rounded-xl border border-uncertain/40 bg-uncertain-soft/70 p-3.5 text-sm">
          <TriangleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-uncertain" />
          <p>{report.statusNote ?? "This perspective did not finish."}</p>
        </div>
      )}

      {report.findings.length > 0 && (
        <section className="space-y-2.5">
          <h4 className="eyebrow">What this view found</h4>
          <ul className="space-y-2.5">{report.findings.map((f) => <FindingCard key={f.id} finding={f} />)}</ul>
        </section>
      )}

      {report.considerations.length > 0 && (
        <section className="space-y-2.5">
          <h4 className="eyebrow">Points to discuss</h4>
          <ul className="space-y-2.5">{report.considerations.map((f) => <FindingCard key={f.id} finding={f} />)}</ul>
        </section>
      )}

      {report.contradictions.length > 0 && (
        <section className="space-y-2.5">
          <h4 className="eyebrow">Contradictions in the records</h4>
          <ul className="space-y-2">
            {report.contradictions.map((c) => (
              <li key={c.id} className={cn("flex flex-wrap items-start gap-2 rounded-xl border p-3", flagSurface.disagreement)}>
                <FlagMarker flag="disagreement" />
                <p className="min-w-0 flex-1 basis-48 text-sm">{c.description}</p>
                <EvidenceChip itemId={c.id} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.uncertainties.length > 0 && (
        <section className="space-y-2.5">
          <h4 className="eyebrow">What this view is unsure about</h4>
          <ul className="space-y-2">
            {report.uncertainties.map((u) => (
              <li key={u.id} className={cn("space-y-1 rounded-xl border p-3", flagSurface.uncertain)}>
                <div className="flex flex-wrap items-center gap-2">
                  <FlagMarker flag="uncertain" />
                  <ImportanceLabel importance={u.impact} />
                  <EvidenceChip itemId={u.id} className="ml-auto" />
                </div>
                <p className="text-sm">{u.text}</p>
                {u.resolvableBy && <p className="text-xs text-muted-foreground">Could be clarified by: {u.resolvableBy}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.missing.length > 0 && (
        <section className="space-y-2.5">
          <h4 className="eyebrow">What this view couldn’t find</h4>
          <ul className="space-y-2">
            {report.missing.map((m) => (
              <li key={m.id} className={cn("space-y-1 rounded-xl border p-3", flagSurface.missing)}>
                <div className="flex flex-wrap items-center gap-2">
                  <FlagMarker flag="missing" />
                  <EvidenceChip itemId={m.id} className="ml-auto" />
                </div>
                <p className="text-sm font-medium">{m.item}</p>
                <p className="text-sm text-muted-foreground">{m.whyItMatters}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.limitations.length > 0 && (
        <p className="border-t pt-3 text-xs text-muted-foreground">Limits of this view: {report.limitations.join(" ")}</p>
      )}
    </article>
  );
}
