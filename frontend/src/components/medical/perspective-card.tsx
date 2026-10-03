import { ChevronDown, TriangleAlert } from "lucide-react";
import type { Finding, SpecialistReport } from "@/domain/types";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";
import { ConfidenceBadge, FlagMarker, KindTag, flagSurface } from "./markers";

/** One finding from a specialist: a sentence, where it comes from, and its Source. */
export function FindingCard({ finding }: { finding: Finding }) {
  return (
    <li className="space-y-1.5">
      <p className="text-[1.05rem] leading-relaxed">{finding.statement}</p>
      <div className="flex flex-wrap items-center gap-2">
        <KindTag kind={finding.kind} plain />
        <EvidenceChip itemId={finding.id} describes={finding.statement} />
      </div>
    </li>
  );
}

/** Short, plain one-liner shown on the closed row. */
export function perspectiveSummary(report: SpecialistReport): string {
  if (report.status !== "complete") return "This view couldn’t be completed.";
  const top = report.findings.find((f) => f.importance === "high") ?? report.findings[0];
  return top ? top.statement : report.confidence.reason;
}

/**
 * A specialist's view as a simple, expandable reading. Version, tier and
 * routing details are tucked into a small "About this view" disclosure.
 */
export function PerspectiveCard({ report, defaultOpen }: { report: SpecialistReport; defaultOpen?: boolean }) {
  const incomplete = report.status !== "complete";
  return (
    <details className="group py-1" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-start gap-4 py-4">
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="text-xl">{report.name}</h3>
          <p className="line-clamp-2 text-muted-foreground group-open:hidden">{perspectiveSummary(report)}</p>
        </div>
        <ChevronDown aria-hidden className="mt-1.5 size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>

      <div className="space-y-8 pb-8 pt-1">
        {incomplete && (
          <div role="note" className={cn("flex gap-3 rounded-2xl border p-4 text-sm", flagSurface.uncertain)}>
            <TriangleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-uncertain" />
            <p>{report.statusNote ?? "This view did not finish."}</p>
          </div>
        )}

        {report.findings.length > 0 && (
          <section className="space-y-4">
            <h4 className="font-medium">What this view noticed</h4>
            <ul className="space-y-5">{report.findings.map((f) => <FindingCard key={f.id} finding={f} />)}</ul>
          </section>
        )}

        {report.considerations.length > 0 && (
          <section className="space-y-4">
            <h4 className="font-medium">Worth discussing</h4>
            <ul className="space-y-5">{report.considerations.map((f) => <FindingCard key={f.id} finding={f} />)}</ul>
          </section>
        )}

        {report.contradictions.length > 0 && (
          <section className="space-y-3">
            <h4 className="font-medium">Where your records disagree</h4>
            <ul className="space-y-3">
              {report.contradictions.map((c) => (
                <li key={c.id} className={cn("space-y-2 rounded-2xl border p-4", flagSurface.disagreement)}>
                  <FlagMarker flag="disagreement" />
                  <p>{c.description}</p>
                  <EvidenceChip itemId={c.id} describes={c.description} />
                </li>
              ))}
            </ul>
          </section>
        )}

        {report.uncertainties.length > 0 && (
          <section className="space-y-3">
            <h4 className="font-medium">What this view is unsure about</h4>
            <ul className="space-y-3">
              {report.uncertainties.map((u) => (
                <li key={u.id} className={cn("space-y-2 rounded-2xl border p-4", flagSurface.uncertain)}>
                  <FlagMarker flag="uncertain" />
                  <p>{u.text}</p>
                  {u.resolvableBy && <p className="text-sm text-muted-foreground">Could be clarified by: {u.resolvableBy}</p>}
                  <EvidenceChip itemId={u.id} describes={u.text} />
                </li>
              ))}
            </ul>
          </section>
        )}

        {report.missing_info.length > 0 && (
          <section className="space-y-3">
            <h4 className="font-medium">What this view couldn’t find</h4>
            <ul className="space-y-3">
              {report.missing_info.map((m) => (
                <li key={m.id} className={cn("space-y-2 rounded-2xl border p-4", flagSurface.missing)}>
                  <FlagMarker flag="missing" />
                  <p className="font-medium">{m.item}</p>
                  <p className="text-muted-foreground">{m.whyItMatters}</p>
                  <EvidenceChip itemId={m.id} describes={m.item} />
                </li>
              ))}
            </ul>
          </section>
        )}

        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">About this view</summary>
          <div className="mt-3 space-y-2 text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <ConfidenceBadge confidence={report.confidence.overall} />
              <span>{report.confidence.reason}</span>
            </div>
            <p>Included because: {report.routingReason}</p>
            {report.limitations.length > 0 && <p>Limits: {report.limitations.join(" ")}</p>}
            <p className="text-xs">Version {report.version} · reasoning tier {report.tier} · {report.priority}</p>
          </div>
        </details>
      </div>
    </details>
  );
}
