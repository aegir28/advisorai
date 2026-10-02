"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, LogOut, Menu, Plus, Settings, UserRound, type LucideIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useAuth } from "@/features/auth/auth-context";
import { applyTextSize, readTextSize } from "@/features/settings/preferences";
import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import { LoadingState } from "@/components/medical/states";
import { Logo } from "./logo";

interface NavItem {
  href: string;
  label: MessageKey;
  icon: LucideIcon;
  match: (path: string) => boolean;
}

const NAV: NavItem[] = [
  { href: "/dashboard", label: "nav.dashboard", icon: LayoutDashboard, match: (p) => p === "/dashboard" || (p.startsWith("/cases/") && p !== "/cases/new") },
  { href: "/cases/new", label: "nav.newCase", icon: Plus, match: (p) => p === "/cases/new" },
  { href: "/profile", label: "nav.profile", icon: UserRound, match: (p) => p === "/profile" },
  { href: "/settings", label: "nav.settings", icon: Settings, match: (p) => p === "/settings" },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {NAV.map((item) => {
        const active = item.match(pathname);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              active ? "bg-primary text-primary-foreground" : "text-foreground/80 hover:bg-secondary",
            )}
          >
            <item.icon aria-hidden className="size-4.5" />
            {t(item.label)}
          </Link>
        );
      })}
    </nav>
  );
}

function UserBlock() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  return (
    <div className="space-y-3 rounded-xl border bg-card p-3">
      <div className="flex items-center gap-3">
        <span aria-hidden className="grid size-9 place-items-center rounded-full bg-secondary font-heading text-secondary-foreground">
          {(user?.displayName ?? "D").slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{user?.displayName}</p>
          <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="w-full"
        onClick={() => {
          signOut();
          router.push("/");
        }}
      >
        <LogOut aria-hidden data-icon="inline-start" /> {t("nav.signOut")}
      </Button>
    </div>
  );
}

/** Authenticated application frame: sidebar on desktop, sheet menu on mobile. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (status === "anon") router.replace("/login");
  }, [status, router]);

  useEffect(() => {
    applyTextSize(readTextSize());
  }, []);

  if (status !== "authed") {
    return (
      <main id="main" className="mx-auto max-w-3xl p-6">
        <LoadingState rows={2} />
      </main>
    );
  }

  return (
    <div className="mx-auto flex max-w-[88rem]">
      <aside data-no-print className="no-print sticky top-8 hidden h-[calc(100dvh-2rem)] w-64 shrink-0 flex-col justify-between border-r p-4 pb-16 lg:flex">
        <div className="space-y-6">
          <Logo href="/dashboard" className="px-2 pt-2" />
          <Link href="/cases/new" className={cn(buttonVariants({ size: "lg" }), "w-full")}>
            <Plus aria-hidden data-icon="inline-start" /> {t("nav.newCase")}
          </Link>
          <NavLinks />
        </div>
        <UserBlock />
      </aside>

      <div className="min-w-0 flex-1">
        <header data-no-print className="no-print sticky top-8 z-30 flex items-center justify-between border-b bg-background/90 px-4 py-2.5 backdrop-blur lg:hidden">
          <Logo href="/dashboard" />
          <Button variant="outline" size="icon" aria-label={t("nav.menu")} onClick={() => setMenuOpen(true)}>
            <Menu aria-hidden />
          </Button>
        </header>
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetContent side="left" className="w-[18rem] gap-6 p-4">
            <SheetTitle className="sr-only">{t("nav.menu")}</SheetTitle>
            <SheetDescription className="sr-only">Main navigation</SheetDescription>
            <Logo href="/dashboard" className="px-2 pt-2" />
            <NavLinks onNavigate={() => setMenuOpen(false)} />
            <div className="mt-auto">
              <UserBlock />
            </div>
          </SheetContent>
        </Sheet>
        <main id="main" className="px-4 py-6 sm:px-8 sm:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
