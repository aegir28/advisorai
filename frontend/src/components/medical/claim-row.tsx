import { Ban } from "lucide-react";
import type { Claim } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";
import { KindTag, VerificationBadge } from "./markers";

/** One verified claim: status, why, and what it was checked against. */
export function ClaimRow({ claim, sourceTitle }: { claim: Claim; sourceTitle: (id: string) => string }) {
  return (
    <li className={cn("paper space-y-3 p-4", claim.removed && "border-dashed bg-muted/40")}>
      <div className="flex flex-wrap items-center gap-2">
        <VerificationBadge status={claim.status} />
        <KindTag kind={claim.kind} />
        <span className="text-xs text-muted-foreground">{claim.id}</span>
        {claim.removed && (
          <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-missing/50 px-2 py-0.5 text-xs font-medium text-missing">
            <Ban aria-hidden className="size-3" /> Removed before the report
          </span>
        )}
      </div>
      <p className={cn("leading-relaxed", claim.removed && "text-muted-foreground line-through decoration-muted-foreground/50")}>{claim.text}</p>
      <p className="text-sm text-muted-foreground">{claim.removalReason ?? claim.rationale}</p>
      <p className="text-xs text-muted-foreground">{tk(`verify.${claim.status}.long`)}</p>
      {(claim.patientFactIds.length > 0 || claim.externalSourceIds.length > 0) && (
        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <span className="eyebrow">Checked against</span>
          {claim.patientFactIds.map((id) => <EvidenceChip key={id} itemId={id} label={`Your record · ${id}`} />)}
          {claim.externalSourceIds.map((id) => <EvidenceChip key={id} itemId={id} label={sourceTitle(id)} className="max-w-full truncate" />)}
        </div>
      )}
    </li>
  );
}
