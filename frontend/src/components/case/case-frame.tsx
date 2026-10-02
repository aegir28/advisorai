"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, ArrowRight, ChevronLeft } from "lucide-react";
import { EmptyState, LoadingState } from "@/components/medical/states";
import { SyntheticTag } from "@/components/medical/markers";
import { buttonVariants } from "@/components/ui/button";
import { useCase } from "@/features/case/hooks";
import { STAGES, stageIndexFor } from "@/features/case/stages";
import { sexLabel } from "@/lib/format";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { CaseStatusBadge } from "./case-status";

/** Header, stage navigation and next/back footer shared by every case screen. */
export function CaseFrame({ caseId, children }: { caseId: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: c, status } = useCase(caseId);
  const navRef = useRef<HTMLOListElement>(null);

  // Keep the current stage visible in the horizontally scrolling journey nav.
  useEffect(() => {
    const list = navRef.current;
    const active = list?.querySelector<HTMLElement>('[aria-current="page"]');
    if (list && active) list.scrollLeft = active.offsetLeft - list.clientWidth / 2 + active.clientWidth / 2;
  }, [pathname, status]);

  if (status === "loading") return <div className="mx-auto max-w-5xl"><LoadingState rows={2} /></div>;
  if (!c) {
    return (
      <div className="mx-auto max-w-3xl">
        <EmptyState title="We couldn't find that case" body="It may have been deleted, or the link is out of date." action={{ label: "Back to dashboard", href: "/dashboard" }} />
      </div>
    );
  }

  const hasResults = c.status === "complete" || c.status === "partial";
  const idx = stageIndexFor(pathname, caseId);
  const prev = idx > 0 ? STAGES[idx - 1] : null;
  const next = idx >= 0 && idx < STAGES.length - 1 ? STAGES[idx + 1] : null;
  const href = (path: string) => `/cases/${caseId}${path}`;

  return (
    <div className="mx-auto max-w-5xl">
      <div data-no-print className="no-print mb-4 flex flex-wrap items-center justify-between gap-3">
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
          <ChevronLeft aria-hidden className="size-4" /> All cases
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <SyntheticTag />
          <CaseStatusBadge status={c.status} />
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p className="font-heading text-lg text-ink">Case {c.code}</p>
        <p className="text-sm text-muted-foreground">
          {c.ageYears} · {sexLabel(c.sex)} · {c.specialtyLabel}
        </p>
      </div>

      <nav
        aria-label="Case journey"
        data-no-print
        className="no-print sticky top-[5.5rem] z-20 -mx-4 mb-8 border-b bg-background/95 px-4 backdrop-blur sm:-mx-8 sm:px-8 lg:top-8"
      >
        <ol ref={navRef} className="relative flex gap-1 overflow-x-auto py-2 [scrollbar-width:thin]">
          {STAGES.map((s, i) => {
            const active = i === idx;
            const dim = s.needsResults && !hasResults;
            return (
              <li key={s.key} className="shrink-0">
                <Link
                  href={href(s.path)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors",
                    active ? "bg-primary text-primary-foreground" : dim ? "text-muted-foreground/70 hover:bg-secondary" : "text-foreground/80 hover:bg-secondary",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "grid size-5 place-items-center rounded-full text-[0.7rem]",
                      active ? "bg-primary-foreground/20" : "bg-muted text-muted-foreground",
                    )}
                  >
                    {i + 1}
                  </span>
                  {t(s.label)}
                </Link>
              </li>
            );
          })}
        </ol>
      </nav>

      {children}

      {idx >= 0 && (
        <div data-no-print className="no-print mt-12 flex flex-wrap items-center justify-between gap-3 border-t pt-6">
          {prev ? (
            <Link href={href(prev.path)} className={cn(buttonVariants({ variant: "outline", size: "lg" }))}>
              <ArrowLeft aria-hidden data-icon="inline-start" /> {t(prev.label)}
            </Link>
          ) : <span />}
          {next && (
            <Link href={href(next.path)} className={cn(buttonVariants({ size: "lg" }))}>
              {t(next.label)} <ArrowRight aria-hidden data-icon="inline-end" />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
