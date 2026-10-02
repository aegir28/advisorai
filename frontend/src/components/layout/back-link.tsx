import Link from "next/link";
import { ChevronLeft } from "lucide-react";

/** Quiet "back to the hub" link for contextual pages. */
export function BackLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} data-no-print className="no-print mb-5 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ChevronLeft aria-hidden className="size-4" /> {children}
    </Link>
  );
}
