"use client";

import { useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { LogoMark } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { BRAND } from "@/config/brand";
import { useAuth } from "@/features/auth/auth-context";

/** Onboarding for people who signed in but have not yet given consent. */
export default function WelcomePage() {
  const router = useRouter();
  const { status, user, acceptConsent } = useAuth();
  const id = useId();
  const [consent, setConsent] = useState(false);

  useEffect(() => {
    if (status === "anon") router.replace("/login");
    if (status === "authed" && user?.consentedAt) router.replace("/home");
  }, [status, user, router]);

  return (
    <main id="main" className="mx-auto flex min-h-[80dvh] max-w-md flex-col items-center justify-center gap-8 px-5 py-12 text-center">
      <title>{`Welcome · ${BRAND.name}`}</title>
      <LogoMark className="size-14" />
      <div className="space-y-3">
        <h1 className="text-4xl">One quick thing{user ? `, ${user.displayName.split(" ")[0]}` : ""}</h1>
        <p className="text-lg text-muted-foreground">Before we start, please read and confirm.</p>
      </div>
      <div className="flex items-start gap-3 rounded-2xl bg-secondary/60 p-4 text-left">
        <Checkbox id={id} checked={consent} onCheckedChange={(v) => setConsent(v === true)} className="mt-1" />
        <Label htmlFor={id} className="block text-sm font-normal leading-relaxed">
          I understand this is a <strong>prototype</strong>: I will only use fictional information, never real medical records. I
          understand {BRAND.name} helps me prepare for a conversation with a doctor and is <strong>not medical advice</strong>.
        </Label>
      </div>
      <Button
        size="lg" className="h-14 w-full rounded-2xl text-base" disabled={!consent}
        onClick={() => { acceptConsent(); router.push("/home"); }}
      >
        Continue <ArrowRight aria-hidden data-icon="inline-end" />
      </Button>
    </main>
  );
}
