import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

export default function NotFound() {
  return (
    <main id="main" className="mx-auto flex min-h-[60dvh] max-w-xl flex-col items-center justify-center gap-4 px-4 text-center">
      <p className="eyebrow">404</p>
      <h1 className="text-4xl">{t("common.notFound")}</h1>
      <p className="text-muted-foreground">The page may have moved, or the link may be out of date.</p>
      <Link href="/" className={cn(buttonVariants({ size: "lg" }))}>Back to the start</Link>
    </main>
  );
}
