"use client";

import Link from "next/link";
import { FileText, Plus } from "lucide-react";
import { CaseRow } from "@/components/case/case-row";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/medical/states";
import { buttonVariants } from "@/components/ui/button";
import { useCases } from "@/features/case/hooks";
import { cn } from "@/lib/utils";

export default function CasesPage() {
  const cases = useCases();
  return (
    <>
      <PageHeader
        title="Your cases"
        actions={
          <Link href="/cases/new" className={cn(buttonVariants({ size: "lg" }), "rounded-2xl")}>
            <Plus aria-hidden data-icon="inline-start" /> New case
          </Link>
        }
      />
      {cases.status === "loading" && <LoadingState rows={3} />}
      {cases.status === "error" && <ErrorState onRetry={cases.reload} />}
      {cases.data?.length === 0 && (
        <EmptyState icon={FileText} title="No cases yet" body="Start a case to add your reports and get a clear summary." action={{ label: "Start a new case", href: "/cases/new" }} />
      )}
      {cases.data && cases.data.length > 0 && (
        <div className="divide-y">{cases.data.map((c) => <CaseRow key={c.id} c={c} />)}</div>
      )}
    </>
  );
}
