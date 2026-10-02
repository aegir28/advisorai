"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { EmptyState, LoadingState } from "@/components/medical/states";
import { useCase } from "@/features/case/hooks";
import { CASE_TABS, activeTabKey } from "@/features/case/stages";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { caseStatusLine, caseTitle } from "./case-row";

/** Title and the five-place case navigation shared by every case screen. */
export function CaseFrame({ caseId, children }: { caseId: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: c, status } = useCase(caseId);
  const navRef = useRef<HTMLOListElement>(null);
  const active = activeTabKey(pathname, caseId);

  // Keep the current tab visible in the horizontally scrolling nav on small screens.
  useEffect(() => {
    const list = navRef.current;
    const el = list?.querySelector<HTMLElement>('[aria-current="page"]');
    if (list && el) list.scrollLeft = el.offsetLeft - list.clientWidth / 2 + el.clientWidth / 2;
  }, [pathname, status]);

  if (status === "loading") return <LoadingState rows={2} />;
  if (!c) {
    return (
      <EmptyState
        title="We couldn’t find that case"
        body="It may have been deleted, or the link is out of date."
        action={{ label: "Back to your cases", href: "/cases" }}
      />
    );
  }

  const started = c.status !== "draft" && c.status !== "awaiting_upload";
  const href = (path: string) => `/cases/${caseId}${path}`;

  return (
    <div>
      <div data-no-print className="no-print mb-6 space-y-2">
        <Link href="/cases" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ChevronLeft aria-hidden className="size-4" /> Cases
        </Link>
        <h1 className="text-3xl sm:text-4xl">{caseTitle(c)}</h1>
        <p className="text-sm text-muted-foreground">
          Case {c.code} · {caseStatusLine[c.status]}
        </p>
      </div>

      {started && (
        <nav aria-label="This case" data-no-print className="no-print sticky top-[4.4rem] z-20 -mx-5 mb-10 border-b bg-background/95 px-5 backdrop-blur">
          <ol ref={navRef} className="flex gap-6 overflow-x-auto [scrollbar-width:none]">
            {CASE_TABS.map((tab) => {
              const on = tab.key === active;
              return (
                <li key={tab.key} className="shrink-0">
                  <Link
                    href={href(tab.path)}
                    aria-current={on ? "page" : undefined}
                    className={cn(
                      "block border-b-2 py-3 text-[0.95rem] font-medium whitespace-nowrap transition-colors",
                      on ? "border-primary text-ink" : "border-transparent text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {t(tab.label)}
                  </Link>
                </li>
              );
            })}
          </ol>
        </nav>
      )}

      {children}
    </div>
  );
}
