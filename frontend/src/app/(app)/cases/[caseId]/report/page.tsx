"use client";

import { useParams } from "next/navigation";
import { Printer } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ResultsGate } from "@/components/case/results-gate";
import { Legend } from "@/components/medical/legend";
import { SyntheticTag } from "@/components/medical/markers";
import { SectionRenderer } from "@/components/report/section-renderer";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/config/brand";
import { useCase, useReport } from "@/features/case/hooks";
import { formatDate, sexLabel } from "@/lib/format";
import { t, tk } from "@/i18n";

export default function ReportPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const report = useReport(caseId);
  const c = useCase(caseId);

  return (
    <>
      {/* Print-only masthead */}
      <div className="print-only mb-4 border-b pb-3">
        <p className="font-heading text-xl">{BRAND.name} · {t("report.title")}</p>
        <p className="text-sm">Prototype on fictional data. {t("disclaimer.short")}</p>
      </div>

      <PageHeader
        eyebrow="Report"
        title={t("report.title")}
        description={
          c.data ? (
            <>
              Case {c.data.code} · {c.data.ageYears}, {sexLabel(c.data.sex)} · written in plain language from the reviewed summary.
            </>
          ) : undefined
        }
        actions={
          <Button variant="outline" size="lg" onClick={() => window.print()}>
            <Printer aria-hidden data-icon="inline-start" /> {t("common.print")}
          </Button>
        }
      />

      <ResultsGate query={report} caseId={caseId}>
        {(r) => (
          <div className="grid gap-10 xl:grid-cols-[13rem_minmax(0,1fr)]">
            <nav aria-label="Report sections" data-no-print className="no-print hidden xl:block">
              <ol className="sticky top-40 space-y-0.5 text-sm">
                {r.sections.map((s) => (
                  <li key={s.number}>
                    <a href={`#s${s.number}`} className="flex gap-2 rounded-lg px-2 py-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground">
                      <span className="w-5 shrink-0 text-right tabular-nums">{s.number}</span>
                      <span>{tk(`report.s${s.number}`)}</span>
                    </a>
                  </li>
                ))}
              </ol>
            </nav>

            <div className="min-w-0 space-y-10">
              <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                <SyntheticTag />
                <span>{t("report.generated", { date: formatDate(r.generatedAt), run: r.runId })}</span>
              </div>
              <Legend />
              {r.sections.map((s) => <SectionRenderer key={s.number} section={s} caseId={caseId} />)}
            </div>
          </div>
        )}
      </ResultsGate>
    </>
  );
}
