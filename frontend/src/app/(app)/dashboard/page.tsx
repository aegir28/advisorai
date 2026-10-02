"use client";

import Link from "next/link";
import { ArrowRight, FileText, Plus, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { CaseStatusBadge } from "@/components/case/case-status";
import { EmptyState, ErrorState, LoadingState } from "@/components/medical/states";
import { SyntheticTag } from "@/components/medical/markers";
import { buttonVariants } from "@/components/ui/button";
import { useCases } from "@/features/case/hooks";
import { useAuth } from "@/features/auth/auth-context";
import { formatDate, sexLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { scenarioBlurbs } from "@/mocks/scenarios";

export default function DashboardPage() {
  const { user } = useAuth();
  const cases = useCases();

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow="Dashboard"
        title={`Welcome${user ? `, ${user.displayName}` : ""}`}
        description="Pick up where you left off, or start a new case. Everything below is synthetic demo data."
        actions={
          <Link href="/cases/new" className={cn(buttonVariants({ size: "lg" }))}>
            <Plus aria-hidden data-icon="inline-start" /> Start a new case
          </Link>
        }
      />

      <aside className="mb-8 flex gap-3 rounded-2xl border border-primary/15 bg-accent/60 p-4 text-sm">
        <Sparkles aria-hidden className="mt-0.5 size-5 shrink-0 text-primary" />
        <p>
          <strong className="font-medium">Three fictional cases are ready to explore.</strong> One is complete, one has{" "}
          <em>missing information</em>, and one has <em>conflicting reports</em>. The last two show how AdvisorAI behaves when records
          are incomplete or disagree.
        </p>
      </aside>

      <h2 className="mb-4 text-xl">Your cases</h2>
      {cases.status === "loading" && <LoadingState rows={3} />}
      {cases.status === "error" && <ErrorState onRetry={cases.reload} />}
      {cases.data && cases.data.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No cases yet"
          body="Start a case to add your records and get a plain-language report and personalised questions."
          action={{ label: "Start a new case", href: "/cases/new" }}
        />
      )}
      {cases.data && cases.data.length > 0 && (
        <ul className="grid gap-4 md:grid-cols-2">
          {cases.data.map((c) => (
            <li key={c.id}>
              <Link
                href={`/cases/${c.id}`}
                className="paper group flex h-full flex-col gap-4 p-5 transition-shadow hover:shadow-lg focus-visible:shadow-lg"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-sm font-medium text-muted-foreground">Case {c.code}</span>
                  <CaseStatusBadge status={c.status} />
                </div>
                <div className="space-y-1.5">
                  <h3 className="text-xl leading-snug">{c.concern}</h3>
                  {c.proposedTreatment && (
                    <p className="text-sm text-muted-foreground">
                      Proposed: <span className="text-foreground">{c.proposedTreatment}</span>
                    </p>
                  )}
                </div>
                <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted-foreground">
                  <span>
                    {c.ownerLabel} · {c.ageYears} · {sexLabel(c.sex)}
                  </span>
                  <span>{c.documentCount} documents</span>
                  <span>Updated {formatDate(c.updatedAt)}</span>
                </div>
                <div className="flex items-center justify-between border-t pt-3">
                  <div className="flex items-center gap-2">
                    <SyntheticTag />
                    {c.scenario !== "cardiology" && (
                      <span className="text-xs text-muted-foreground">
                        {scenarioBlurbs[c.scenario].title}
                      </span>
                    )}
                  </div>
                  <span className="inline-flex items-center gap-1 text-sm font-medium text-primary">
                    Open <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
