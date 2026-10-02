"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { Phone, Siren } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { EMERGENCY_NUMBERS } from "@/config/brand";
import type { SafetyCheckResult } from "@/domain/types";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

/**
 * Shown instead of the workflow when the red-flag screen triggers.
 * No case is created and no analysis is queued.
 */
export function UrgentCareScreen({ result }: { result: SafetyCheckResult }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);

  return (
    <section role="alert" aria-labelledby="urgent-title" className="mx-auto max-w-2xl space-y-6 rounded-3xl border-2 border-urgent/40 bg-urgent-soft p-6 sm:p-10">
      <span className="grid size-14 place-items-center rounded-2xl bg-urgent text-white">
        <Siren aria-hidden className="size-7" />
      </span>
      <div className="space-y-3">
        <h1 id="urgent-title" ref={headingRef} tabIndex={-1} className="text-3xl text-ink outline-none sm:text-4xl">
          {t("urgent.title")}
        </h1>
        <p className="text-lg">{t("urgent.body")}</p>
        <p className="text-lg font-medium">{t("urgent.action")}</p>
        {result.category === "self_harm" && <p className="text-lg font-medium">{t("urgent.suicide")}</p>}
      </div>
      <div className="flex flex-wrap gap-3">
        {EMERGENCY_NUMBERS.map((n) => (
          <a key={n} href={`tel:${n}`} className={cn(buttonVariants({ size: "lg" }), "bg-urgent text-white hover:bg-urgent/90")}>
            <Phone aria-hidden data-icon="inline-start" /> Call {n}
          </a>
        ))}
        <Link href="/dashboard" className={cn(buttonVariants({ size: "lg", variant: "outline" }))}>
          Back to my dashboard
        </Link>
      </div>
      <p className="border-t border-urgent/20 pt-4 text-sm text-muted-foreground">{t("urgent.note")}</p>
    </section>
  );
}
