import { BRAND } from "@/config/brand";
import { cn } from "@/lib/utils";

/** Consistent page title block used inside the app. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-6 flex flex-wrap items-end justify-between gap-4", className)}>
      {/* React 19 hoists <title> into <head>, giving every screen its own page title. */}
      <title>{`${title} · ${BRAND.name}`}</title>
      <div className="min-w-0 max-w-2xl space-y-1.5">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="text-3xl leading-tight sm:text-4xl">{title}</h1>
        {description && <div className="text-base text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="no-print flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
