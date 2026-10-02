"use client";

import Link from "next/link";
import { ArrowRight, Plus } from "lucide-react";
import { CaseRow } from "@/components/case/case-row";
import { ErrorState, LoadingState } from "@/components/medical/states";
import { buttonVariants } from "@/components/ui/button";
import { BRAND } from "@/config/brand";
import { useCases } from "@/features/case/hooks";
import { cn } from "@/lib/utils";

export default function HomePage() {
  const cases = useCases();
  const recent = cases.data?.slice(0, 3) ?? [];

  return (
    <div className="space-y-14">
      <title>{`Home · ${BRAND.name}`}</title>
      <section className="space-y-6">
        <h1 className="text-4xl leading-[1.1] sm:text-5xl">Understand your medical case before your next doctor visit.</h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          Add your reports. We’ll review them and prepare a clear summary, plus the questions worth asking.
        </p>
        <Link href="/cases/new" className={cn(buttonVariants({ size: "lg" }), "h-14 rounded-2xl px-7 text-base")}>
          <Plus aria-hidden data-icon="inline-start" /> Start a new case
        </Link>
      </section>

      <section aria-labelledby="recent-h" className="space-y-3">
        <h2 id="recent-h" className="text-xl text-muted-foreground">Your recent cases</h2>
        {cases.status === "loading" && <LoadingState rows={2} />}
        {cases.status === "error" && <ErrorState onRetry={cases.reload} />}
        {cases.status === "success" && recent.length === 0 && (
          <p className="text-muted-foreground">No cases yet. Your first one takes about two minutes to set up.</p>
        )}
        {recent.length > 0 && (
          <div className="divide-y">
            {recent.map((c) => <CaseRow key={c.id} c={c} />)}
          </div>
        )}
        {(cases.data?.length ?? 0) > 3 && (
          <Link href="/cases" className="inline-flex items-center gap-1 pt-2 text-sm font-medium text-primary underline-offset-4 hover:underline">
            See all cases <ArrowRight aria-hidden className="size-4" />
          </Link>
        )}
      </section>
    </div>
  );
}
