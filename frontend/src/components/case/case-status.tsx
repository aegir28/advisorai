import { CircleAlert, CircleCheck, CircleDashed, LoaderCircle, TriangleAlert, type LucideIcon } from "lucide-react";
import type { CaseStatus } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";

const styles: Record<CaseStatus, { icon: LucideIcon; cls: string; spin?: boolean }> = {
  draft: { icon: CircleDashed, cls: "bg-muted text-muted-foreground border-border" },
  awaiting_upload: { icon: CircleDashed, cls: "bg-muted text-muted-foreground border-border" },
  processing: { icon: LoaderCircle, cls: "bg-fact-soft text-fact border-fact/25", spin: true },
  complete: { icon: CircleCheck, cls: "bg-evidence-soft text-evidence border-evidence/25" },
  partial: { icon: TriangleAlert, cls: "bg-uncertain-soft text-uncertain border-uncertain/30" },
  failed: { icon: CircleAlert, cls: "bg-urgent-soft text-urgent border-urgent/30" },
};

export function CaseStatusBadge({ status, className }: { status: CaseStatus; className?: string }) {
  const { icon: Icon, cls, spin } = styles[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", cls, className)}>
      <Icon aria-hidden className={cn("size-3.5", spin && "animate-spin motion-reduce:animate-none")} />
      {tk(`caseStatus.${status}`)}
    </span>
  );
}
