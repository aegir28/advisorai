"use client";

import Link from "next/link";
import { ErrorState } from "@/components/medical/states";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main id="main" className="mx-auto max-w-xl space-y-4 px-4 py-16">
      <ErrorState onRetry={reset} />
      <div className="text-center">
        <Link href="/dashboard" className={cn(buttonVariants({ variant: "ghost" }))}>Go to my dashboard</Link>
      </div>
    </main>
  );
}
