import { BRAND } from "@/config/brand";
import { cn } from "@/lib/utils";

/**
 * Quiet heading for screens inside a case (the case title is already the h1).
 * One title, one calm sentence, an optional single action.
 */
export function PageIntro({
  title,
  children,
  action,
  className,
}: {
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-8 flex flex-wrap items-end justify-between gap-4", className)}>
      <title>{`${title} · ${BRAND.name}`}</title>
      <div className="min-w-0 max-w-xl space-y-2">
        <h2 className="text-2xl sm:text-3xl">{title}</h2>
        {children && <div className="text-muted-foreground">{children}</div>}
      </div>
      {action && <div className="no-print flex flex-wrap items-center gap-2">{action}</div>}
    </div>
  );
}
