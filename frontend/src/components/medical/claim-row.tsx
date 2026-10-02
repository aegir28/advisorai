import type { Claim } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";
import { VerificationBadge } from "./markers";

/** One checked statement: what it says, how it fared, and what it was checked against. */
export function ClaimRow({ claim, sourceTitle }: { claim: Claim; sourceTitle: (id: string) => string }) {
  return (
    <li className="space-y-2.5">
      <p className={cn("text-[1.05rem] leading-relaxed", claim.removed && "text-muted-foreground line-through decoration-muted-foreground/50")}>{claim.text}</p>
      <div className="flex flex-wrap items-center gap-2">
        <VerificationBadge status={claim.status} />
        {claim.removed && <span className="text-xs font-medium text-missing">Removed before your report</span>}
      </div>
      <p className="text-sm text-muted-foreground">{claim.removalReason ?? claim.rationale}</p>
      {(claim.patientFactIds.length > 0 || claim.externalSourceIds.length > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          {claim.patientFactIds.map((id) => <EvidenceChip key={id} itemId={id} label="Your report" />)}
          {claim.externalSourceIds.map((id) => <EvidenceChip key={id} itemId={id} label={sourceTitle(id)} className="max-w-full truncate" />)}
        </div>
      )}
      <span className="sr-only">{tk(`verify.${claim.status}.long`)}</span>
    </li>
  );
}
