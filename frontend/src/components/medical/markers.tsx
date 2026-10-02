import {
  ArrowLeftRight,
  BookOpen,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleHelp,
  FileSearch,
  FileText,
  Info,
  Sparkles,
  Split,
  type LucideIcon,
} from "lucide-react";
import type { Confidence, ContentKind, Flag, Importance, VerificationStatus } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";

/**
 * The visual vocabulary that keeps uncertainty, gaps and disagreement visible.
 * Every marker pairs an icon with text; colour is never the only signal.
 * Hues are intentionally not red/green, so nothing reads as "right or wrong".
 */

const pill = "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium leading-5 whitespace-nowrap";

// ── Kinds: patient_fact | interpretation | external_evidence ──
const kindStyle: Record<ContentKind, { icon: LucideIcon; cls: string; accent: string }> = {
  patient_fact: { icon: FileText, cls: "bg-fact-soft text-fact border-fact/20", accent: "border-l-fact" },
  interpretation: { icon: Sparkles, cls: "bg-interp-soft text-interp border-interp/20", accent: "border-l-interp" },
  external_evidence: { icon: BookOpen, cls: "bg-evidence-soft text-evidence border-evidence/20", accent: "border-l-evidence" },
  template: { icon: Info, cls: "bg-muted text-muted-foreground border-border", accent: "border-l-border" },
};

export const kindAccent = (kind: ContentKind) => kindStyle[kind].accent;

const kindText: Record<ContentKind, string> = {
  patient_fact: "text-fact",
  interpretation: "text-interp",
  external_evidence: "text-evidence",
  template: "text-muted-foreground",
};

/**
 * Where a statement comes from. `plain` is the quiet inline form used inside
 * reading text (icon + words, no pill), so documents stay calm to read.
 */
export function KindTag({ kind, className, iconOnly, plain }: { kind: ContentKind; className?: string; iconOnly?: boolean; plain?: boolean }) {
  const { icon: Icon, cls } = kindStyle[kind];
  return (
    <span
      className={cn(plain ? cn("inline-flex shrink-0 items-center gap-1 text-xs font-medium", kindText[kind]) : cn(pill, cls), className)}
      title={tk(`kind.${kind}.long`)}
    >
      <Icon aria-hidden className="size-3.5" />
      <span className={iconOnly ? "sr-only" : undefined}>{tk(`kind.${kind}`)}</span>
    </span>
  );
}

// ── Flags: uncertain | missing | disagreement ──
const flagStyle: Record<Flag, { icon: LucideIcon; cls: string }> = {
  uncertain: { icon: CircleHelp, cls: "bg-uncertain-soft text-uncertain border-uncertain/30" },
  missing: { icon: FileSearch, cls: "bg-missing-soft text-missing border-missing/50 border-dashed" },
  disagreement: { icon: Split, cls: "bg-disagree-soft text-disagree border-disagree/30" },
};

export function FlagMarker({ flag, className, label }: { flag: Flag; className?: string; label?: string }) {
  const { icon: Icon, cls } = flagStyle[flag];
  return (
    <span className={cn(pill, cls, className)} title={tk(`flag.${flag}.long`)}>
      <Icon aria-hidden className="size-3.5" />
      {label ?? tk(`flag.${flag}`)}
    </span>
  );
}

/** Soft tinted surface classes for callouts matching a flag. */
export const flagSurface: Record<Flag, string> = {
  uncertain: "border-uncertain/30 bg-uncertain-soft/60",
  missing: "border-dashed border-missing/50 bg-missing-soft/70",
  disagreement: "border-disagree/30 bg-disagree-soft/60",
};

// ── Confidence ──
const confidenceDots: Record<Confidence, number> = { high: 3, moderate: 2, low: 1 };

export function ConfidenceBadge({ confidence, className }: { confidence: Confidence; className?: string }) {
  const filled = confidenceDots[confidence];
  return (
    <span className={cn(pill, "border-border bg-card text-muted-foreground", className)}>
      <span aria-hidden className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span key={i} className={cn("size-1.5 rounded-full", i < filled ? "bg-primary" : "bg-border")} />
        ))}
      </span>
      {tk(`confidence.${confidence}`)}
    </span>
  );
}

export function ImportanceLabel({ importance }: { importance: Importance }) {
  return <span className="text-xs text-muted-foreground">{tk(`importance.${importance}`)}</span>;
}

// ── Verification status ──
const verifyStyle: Record<VerificationStatus, { icon: LucideIcon; cls: string }> = {
  supported: { icon: CircleCheck, cls: "bg-evidence-soft text-evidence border-evidence/25" },
  partially_supported: { icon: CircleDot, cls: "bg-fact-soft text-fact border-fact/25" },
  unclear: { icon: CircleHelp, cls: "bg-uncertain-soft text-uncertain border-uncertain/30" },
  contradicted: { icon: ArrowLeftRight, cls: "bg-disagree-soft text-disagree border-disagree/30" },
  insufficient_evidence: { icon: CircleDashed, cls: "bg-missing-soft text-missing border-missing/50 border-dashed" },
};

export function VerificationBadge({ status, className }: { status: VerificationStatus; className?: string }) {
  const { icon: Icon, cls } = verifyStyle[status];
  return (
    <span className={cn(pill, cls, className)} title={tk(`verify.${status}.long`)}>
      <Icon aria-hidden className="size-3.5" />
      {tk(`verify.${status}`)}
    </span>
  );
}

export function SyntheticTag({ className }: { className?: string }) {
  return <span className={cn(pill, "border-border bg-muted text-muted-foreground", className)}>{tk("common.synthetic")}</span>;
}
