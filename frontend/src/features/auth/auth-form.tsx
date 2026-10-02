"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Mail, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BRAND } from "@/config/brand";
import { t } from "@/i18n";
import { DEMO_OTP, useAuth } from "./auth-context";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Passwordless email-code flow (mirrors the blueprint's Supabase email OTP).
 * No email is sent; the demo code is shown on screen.
 */
export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const { status, signIn } = useAuth();
  const ids = { email: useId(), code: useId(), consent: useId(), err: useId() };
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "authed") router.replace("/dashboard");
  }, [status, router]);

  const submitEmail = (e: React.FormEvent) => {
    e.preventDefault();
    if (!EMAIL_RE.test(email.trim())) return setError("Please enter a valid email address.");
    if (mode === "signup" && !consent) return setError("Please confirm the consent box to continue.");
    setError(null);
    setStep("code");
  };

  const submitCode = (e: React.FormEvent) => {
    e.preventDefault();
    if (code.trim() !== DEMO_OTP) return setError(`That code didn't match. In this prototype the code is ${DEMO_OTP}.`);
    signIn(email.trim(), mode === "signup" ? new Date().toISOString() : undefined);
    router.push("/dashboard");
  };

  const demoUser = () => {
    signIn("demo@advisorai.test", new Date().toISOString());
    router.push("/dashboard");
  };

  return (
    <div className="paper w-full max-w-md space-y-6 p-6 sm:p-8">
      <div className="space-y-2">
        <h1 className="text-3xl">{mode === "signup" ? "Create your space" : "Welcome back"}</h1>
        <p className="text-muted-foreground">
          {step === "email"
            ? mode === "signup"
              ? `Start preparing for your next medical conversation with ${BRAND.name}.`
              : "We'll send a one-time code to your email. No password needed."
            : `Enter the 6-digit code for ${email}.`}
        </p>
      </div>

      {step === "email" ? (
        <form onSubmit={submitEmail} noValidate className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor={ids.email}>Email address</Label>
            <Input
              id={ids.email} type="email" autoComplete="email" inputMode="email" placeholder="you@example.com"
              value={email} onChange={(e) => setEmail(e.target.value)}
              aria-invalid={!!error && !EMAIL_RE.test(email.trim())} aria-describedby={error ? ids.err : undefined}
            />
          </div>

          {mode === "signup" && (
            <div className="flex items-start gap-3 rounded-xl border bg-secondary/50 p-3.5">
              <Checkbox id={ids.consent} checked={consent} onCheckedChange={(v) => setConsent(v === true)} className="mt-1" />
              <Label htmlFor={ids.consent} className="block text-sm font-normal leading-relaxed">
                I understand this is a <strong>prototype</strong>. I will only use fictional information, never real medical records. I
                understand {BRAND.name} prepares me for a conversation with a doctor and is <strong>not medical advice</strong>.
              </Label>
            </div>
          )}

          {error && <p id={ids.err} role="alert" className="text-sm font-medium text-destructive">{error}</p>}

          <Button type="submit" size="lg" className="w-full">
            <Mail aria-hidden data-icon="inline-start" /> Send me a code
          </Button>
        </form>
      ) : (
        <form onSubmit={submitCode} noValidate className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor={ids.code}>One-time code</Label>
            <Input
              id={ids.code} inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="123456"
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              aria-invalid={!!error} aria-describedby={ids.err} className="text-center font-mono text-lg tracking-[0.4em]"
            />
            <p id={ids.err} className="text-sm text-muted-foreground" role={error ? "alert" : undefined}>
              {error ?? `Prototype: no email is sent. Use the demo code ${DEMO_OTP}.`}
            </p>
          </div>
          <Button type="submit" size="lg" className="w-full">
            Continue <ArrowRight aria-hidden data-icon="inline-end" />
          </Button>
          <Button type="button" variant="ghost" className="w-full" onClick={() => { setStep("email"); setError(null); }}>
            {t("common.back")}
          </Button>
        </form>
      )}

      <div className="space-y-3 border-t pt-5 text-center text-sm">
        <Button type="button" variant="outline" className="w-full" onClick={demoUser}>
          <ShieldCheck aria-hidden data-icon="inline-start" /> Skip ahead as a demo user
        </Button>
        {mode === "signup" ? (
          <p className="text-muted-foreground">
            Already have a space?{" "}
            <Link href="/login" className="font-medium text-primary underline underline-offset-4">{t("nav.signIn")}</Link>
          </p>
        ) : (
          <p className="text-muted-foreground">
            New here?{" "}
            <Link href="/signup" className="font-medium text-primary underline underline-offset-4">Create your space</Link>
          </p>
        )}
      </div>
    </div>
  );
}
