import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Logo } from "@/components/layout/logo";
import { BRAND } from "@/config/brand";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="sticky top-8 z-30 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Logo />
          <nav aria-label="Primary" className="flex items-center gap-1 sm:gap-2">
            <Link href="/#how-it-works" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-foreground/80 hover:bg-secondary sm:block">
              {t("nav.howItWorks")}
            </Link>
            <Link href="/#safety" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-foreground/80 hover:bg-secondary sm:block">
              {t("nav.safety")}
            </Link>
            <Link href="/login" className={cn(buttonVariants({ variant: "ghost" }))}>
              {t("nav.signIn")}
            </Link>
            <Link href="/signup" className={cn(buttonVariants())}>
              {t("nav.signUp")}
            </Link>
          </nav>
        </div>
      </header>
      <main id="main">{children}</main>
      <footer className="border-t bg-card/60 pb-14">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-8 text-sm text-muted-foreground sm:px-6">
          <p>
            © {new Date().getFullYear()} {BRAND.name}. Prototype built on fictional data.
          </p>
          <p className="max-w-md">{t("disclaimer.short")}</p>
        </div>
      </footer>
    </>
  );
}
