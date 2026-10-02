import Link from "next/link";
import { BRAND } from "@/config/brand";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8", className)}>
      <rect width="32" height="32" rx="9" fill="var(--primary)" />
      {/* An open page with a guiding line: preparation, not diagnosis */}
      <path d="M9 22.5 16 8l7 14.5" fill="none" stroke="var(--primary-foreground)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 18.2h8" stroke="var(--primary-foreground)" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="16" cy="8" r="1.6" fill="oklch(0.85 0.09 90)" />
    </svg>
  );
}

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("inline-flex items-center gap-2.5 rounded-lg", className)} aria-label={`${BRAND.name} home`}>
      <LogoMark />
      <span className="font-heading text-xl font-semibold tracking-tight text-ink">{BRAND.name}</span>
    </Link>
  );
}
