"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FolderOpen, House, UserRound, type LucideIcon } from "lucide-react";
import { LoadingState } from "@/components/medical/states";
import { useAuth } from "@/features/auth/auth-context";
import { applyTextSize, readTextSize } from "@/features/settings/preferences";
import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import { Logo } from "./logo";

interface NavItem {
  href: string;
  label: MessageKey;
  icon: LucideIcon;
  match: (path: string) => boolean;
}

/** Three places only. Everything else lives inside a case. */
const NAV: NavItem[] = [
  { href: "/home", label: "nav.home", icon: House, match: (p) => p === "/home" },
  { href: "/cases", label: "nav.cases", icon: FolderOpen, match: (p) => p === "/cases" || p.startsWith("/cases/") },
  { href: "/profile", label: "nav.profile", icon: UserRound, match: (p) => p === "/profile" },
];

/** Authenticated frame: a slim top bar on desktop, a bottom bar on mobile. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anon") router.replace("/login");
    else if (status === "authed" && user && !user.consentedAt) router.replace("/welcome");
  }, [status, user, router]);

  useEffect(() => {
    applyTextSize(readTextSize());
  }, []);

  if (status !== "authed" || !user?.consentedAt) {
    return (
      <main id="main" className="mx-auto max-w-2xl p-6">
        <LoadingState rows={2} />
      </main>
    );
  }

  return (
    <>
      <header data-no-print className="no-print sticky top-8 z-30 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-5 py-3">
          <Logo href="/home" />
          <nav aria-label="Main" className="hidden items-center gap-1 sm:flex">
            {NAV.map((item) => {
              const active = item.match(pathname);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                    active ? "bg-secondary text-secondary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {t(item.label)}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-3xl px-5 pb-28 pt-8 sm:pb-24 sm:pt-12">
        {children}
        <p className="mt-16 text-center text-xs text-muted-foreground sm:hidden">{t("disclaimer.short")}</p>
      </main>

      {/* Mobile bottom navigation */}
      <nav
        aria-label="Main"
        data-no-print
        className="no-print fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
      >
        {NAV.map((item) => {
          const active = item.match(pathname);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn("flex flex-col items-center gap-0.5 py-2.5 text-xs font-medium", active ? "text-primary" : "text-muted-foreground")}
            >
              <item.icon aria-hidden className="size-5" />
              {t(item.label)}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
