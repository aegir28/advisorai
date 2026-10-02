import { t } from "@/i18n";
import type { Flag, FactKind } from "@/domain/types";
import { FlagMarker, KindTag } from "./markers";

const KINDS: FactKind[] = ["patient_fact", "interpretation", "external_evidence"];
const FLAGS: Flag[] = ["uncertain", "missing", "disagreement"];

/** "How to read this": explains the visual vocabulary once, everywhere it's used. */
export function Legend({ className }: { className?: string }) {
  return (
    <details className={`paper group p-4 ${className ?? ""}`} data-no-print>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium">
        <span>How to read this page</span>
        <span aria-hidden className="text-muted-foreground transition-transform group-open:rotate-180">⌄</span>
      </summary>
      <div className="mt-4 grid gap-6 text-sm sm:grid-cols-2">
        <div className="space-y-3">
          <p className="eyebrow">Where a statement comes from</p>
          {KINDS.map((k) => (
            <div key={k} className="flex flex-wrap items-start gap-2">
              <KindTag kind={k} />
              <span className="min-w-0 flex-1 text-muted-foreground">{t(`kind.${k}.long` as const)}</span>
            </div>
          ))}
        </div>
        <div className="space-y-3">
          <p className="eyebrow">Always kept visible</p>
          {FLAGS.map((f) => (
            <div key={f} className="flex flex-wrap items-start gap-2">
              <FlagMarker flag={f} />
              <span className="min-w-0 flex-1 text-muted-foreground">{t(`flag.${f}.long` as const)}</span>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}
