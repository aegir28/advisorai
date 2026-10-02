import { FlaskConical } from "lucide-react";
import { BRAND } from "@/config/brand";
import { t } from "@/i18n";

/** Persistent on every screen: this is a prototype on fictional data. */
export function SafetyBanner() {
  if (!BRAND.isPrototype) return null;
  return (
    <div
      role="region"
      aria-label="Prototype notice"
      className="no-print sticky top-0 z-50 border-b border-ink/20 bg-ink px-3 py-1.5 text-center text-xs text-background sm:text-[0.8rem]"
    >
      <FlaskConical aria-hidden className="mr-1.5 inline size-3.5 -translate-y-px" />
      <span className="hidden sm:inline">{t("banner.demo")}</span>
      <span className="sm:hidden">{t("banner.short")}</span>
    </div>
  );
}
