"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowRight, Printer } from "lucide-react";
import { ResultsGate } from "@/components/case/results-gate";
import { PageIntro } from "@/components/layout/page-intro";
import { Legend } from "@/components/medical/legend";
import { ReportView } from "@/components/report/report-view";
import { Button, buttonVariants } from "@/components/ui/button";
import { BRAND } from "@/config/brand";
import { useReport } from "@/features/case/hooks";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";

export default function ReportPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const report = useReport(caseId);

  return (
    <>
      {/* Print-only masthead */}
      <div className="print-only mb-4 border-b pb-3">
        <p className="font-heading text-xl">{BRAND.name} · {t("report.title")}</p>
        <p className="text-sm">Prototype on fictional data. {t("disclaimer.short")}</p>
      </div>

      <PageIntro
        title={t("report.title")}
        action={
          report.data ? (
            <Button variant="outline" onClick={() => window.print()}>
              <Printer aria-hidden data-icon="inline-start" /> {t("common.print")}
            </Button>
          ) : undefined
        }
      >
        {report.data ? t("report.generated", { date: formatDate(report.data.generatedAt), run: report.data.runId }) : "A plain-language summary of your case."}
      </PageIntro>

      <ResultsGate query={report} caseId={caseId}>
        {(r) => (
          <div className="space-y-10">
            <ReportView report={r} caseId={caseId} />
            <Legend />
            <div className="no-print border-t pt-10">
              <Link href={`/cases/${caseId}/questions`} className={cn(buttonVariants({ size: "lg" }), "h-14 rounded-2xl px-8 text-base")}>
                See what to ask your doctors <ArrowRight aria-hidden data-icon="inline-end" />
              </Link>
            </div>
          </div>
        )}
      </ResultsGate>
    </>
  );
}
