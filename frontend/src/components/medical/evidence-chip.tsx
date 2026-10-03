"use client";

import Link from "next/link";
import { Link2 } from "lucide-react";
import { useTraceContext } from "@/features/trace/trace-context";
import { evidenceAriaLabel } from "@/lib/evidence-label";
import { cn } from "@/lib/utils";

/**
 * Small "source" chip. Opens the global traceability drawer for any item ID
 * (report sentence, specialist finding, claim, fact, timeline event, ...).
 */
export function EvidenceChip({
  itemId,
  label = "Source",
  describes,
  className,
}: {
  itemId: string;
  label?: string;
  /** The statement this source supports, in plain words. Used only for the accessible name. */
  describes?: string;
  className?: string;
}) {
  const { hrefFor, activeId } = useTraceContext();
  return (
    <Link
      href={hrefFor(itemId)}
      scroll={false}
      data-no-print
      aria-label={evidenceAriaLabel(label, describes)}
      aria-current={activeId === itemId ? "true" : undefined}
      className={cn(
        "no-print inline-flex shrink-0 items-center gap-1 rounded-full border border-primary/25 bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground transition-colors hover:bg-primary hover:text-primary-foreground",
        activeId === itemId && "bg-primary text-primary-foreground",
        className,
      )}
    >
      <Link2 aria-hidden className="size-3" />
      {label}
    </Link>
  );
}
