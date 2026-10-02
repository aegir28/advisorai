"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/layout/logo";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { BRAND } from "@/config/brand";
import { useAuth } from "@/features/auth/auth-context";
import { GoogleSignInButton } from "@/features/auth/google-sign-in";

export default function SignupPage() {
  const router = useRouter();
  const { status } = useAuth();
  const consentId = useId();
  const [consent, setConsent] = useState(false);
  useEffect(() => {
    if (status === "authed") router.replace("/home");
  }, [status, router]);

  return (
    <div className="mx-auto flex min-h-[70dvh] max-w-md flex-col items-center justify-center gap-8 px-5 py-12 text-center">
      <title>{`Get started · ${BRAND.name}`}</title>
      <LogoMark className="size-14" />
      <div className="space-y-3">
        <h1 className="text-4xl">Create your space</h1>
        <p className="text-lg text-muted-foreground">One tap to start. No new password to remember.</p>
      </div>

      <div className="w-full space-y-5 text-left">
        <div className="flex items-start gap-3 rounded-2xl bg-secondary/60 p-4">
          <Checkbox id={consentId} checked={consent} onCheckedChange={(v) => setConsent(v === true)} className="mt-1" />
          <Label htmlFor={consentId} className="block text-sm font-normal leading-relaxed">
            I understand this is a <strong>prototype</strong>: I will only use fictional information, never real medical records. I
            understand {BRAND.name} helps me prepare for a conversation with a doctor and is <strong>not medical advice</strong>.
          </Label>
        </div>
        <GoogleSignInButton consentGiven={consent} disabled={!consent} />
        {!consent && <p className="text-center text-sm text-muted-foreground">Tick the box above to continue.</p>}
      </div>

      <p className="text-sm text-muted-foreground">
        Already have a space?{" "}
        <Link href="/login" className="font-medium text-primary underline underline-offset-4">Sign in</Link>
      </p>
    </div>
  );
}
