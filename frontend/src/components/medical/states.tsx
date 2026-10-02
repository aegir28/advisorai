import Link from "next/link";
import { CircleAlert, Inbox, RefreshCcw, TriangleAlert, type LucideIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon = Inbox,
  title,
  body,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  body?: string;
  action?: { label: string; href: string };
  className?: string;
}) {
  return (
    <div className={cn("paper flex flex-col items-center gap-3 px-6 py-12 text-center", className)} role="status">
      <span className="grid size-12 place-items-center rounded-full bg-secondary text-secondary-foreground">
        <Icon aria-hidden className="size-6" />
      </span>
      <h2 className="text-xl">{title}</h2>
      {body && <p className="max-w-md text-muted-foreground">{body}</p>}
      {action && (
        <Link href={action.href} className={cn(buttonVariants({ size: "lg" }), "mt-2")}>
          {action.label}
        </Link>
      )}
    </div>
  );
}

export function ErrorState({ title, body, onRetry }: { title?: string; body?: string; onRetry?: () => void }) {
  return (
    <div className="paper flex flex-col items-center gap-3 border-destructive/30 px-6 py-12 text-center" role="alert">
      <span className="grid size-12 place-items-center rounded-full bg-urgent-soft text-urgent">
        <CircleAlert aria-hidden className="size-6" />
      </span>
      <h2 className="text-xl">{title ?? t("common.somethingWrong")}</h2>
      <p className="max-w-md text-muted-foreground">{body ?? t("common.somethingWrongBody")}</p>
      {onRetry && (
        <Button variant="outline" size="lg" onClick={onRetry}>
          <RefreshCcw aria-hidden data-icon="inline-start" /> {t("common.retry")}
        </Button>
      )}
    </div>
  );
}

/** A calm notice for partial results. Never hides the gap. */
export function PartialNotice({ title, children, tone = "uncertain" }: { title: string; children?: React.ReactNode; tone?: "uncertain" | "missing" }) {
  return (
    <div
      role="note"
      className={cn(
        "flex gap-3 rounded-xl border p-4",
        tone === "uncertain" ? "border-uncertain/30 bg-uncertain-soft/70" : "border-dashed border-missing/50 bg-missing-soft",
      )}
    >
      <TriangleAlert aria-hidden className={cn("mt-0.5 size-5 shrink-0", tone === "uncertain" ? "text-uncertain" : "text-missing")} />
      <div className="space-y-1 text-sm">
        <p className="font-medium text-ink">{title}</p>
        {children && <div className="text-muted-foreground">{children}</div>}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-lg bg-muted", className)} />;
}

export function LoadingState({ label, rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="space-y-4">
      <span className="sr-only">{label ?? t("common.loading")}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="paper space-y-3 p-5">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      ))}
    </div>
  );
}
