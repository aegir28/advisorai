"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "./auth-context";

/** A neutral "G" mark. The real flow will use Google's official button. */
function GMark() {
  return (
    <span aria-hidden className="grid size-6 place-items-center rounded-full border bg-white font-sans text-sm font-semibold text-[#4285F4]">G</span>
  );
}

const DEMO_ACCOUNT = { email: "demo@advisorai.test", displayName: "Demo User" };

/**
 * Stand-in for "Continue with Google". It opens a simulated account chooser so
 * the flow feels like the future OAuth redirect. No Google account is used.
 */
export function GoogleSignInButton({ consentGiven, disabled, label = "Continue with Google" }: { consentGiven?: boolean; disabled?: boolean; label?: string }) {
  const router = useRouter();
  const { signIn } = useAuth();
  const [open, setOpen] = useState(false);

  const choose = () => {
    signIn(DEMO_ACCOUNT, consentGiven);
    setOpen(false);
    router.push("/home");
  };

  return (
    <>
      <Button type="button" variant="outline" size="lg" className="h-14 w-full gap-3 rounded-2xl bg-card text-base" disabled={disabled} onClick={() => setOpen(true)}>
        <GMark /> {label}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">Choose an account</DialogTitle>
            <DialogDescription>
              Prototype: this simulates Google sign-in. No Google account is used and nothing is sent anywhere.
            </DialogDescription>
          </DialogHeader>
          <button
            type="button" onClick={choose}
            className="flex items-center gap-3 rounded-xl border bg-card p-3 text-left transition-colors hover:bg-secondary"
          >
            <span aria-hidden className="grid size-10 place-items-center rounded-full bg-secondary font-heading text-secondary-foreground">D</span>
            <span className="min-w-0 flex-1">
              <span className="block font-medium">{DEMO_ACCOUNT.displayName}</span>
              <span className="block truncate text-sm text-muted-foreground">{DEMO_ACCOUNT.email}</span>
            </span>
            <ChevronRight aria-hidden className="size-4 text-muted-foreground" />
          </button>
        </DialogContent>
      </Dialog>
    </>
  );
}
