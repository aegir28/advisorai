"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/layout/logo";
import { BRAND } from "@/config/brand";
import { useAuth } from "@/features/auth/auth-context";
import { GoogleSignInButton } from "@/features/auth/google-sign-in";

export default function LoginPage() {
  const router = useRouter();
  const { status } = useAuth();
  useEffect(() => {
    if (status === "authed") router.replace("/home");
  }, [status, router]);

  return (
    <div className="mx-auto flex min-h-[70dvh] max-w-md flex-col items-center justify-center gap-8 px-5 py-12 text-center">
      <title>{`Sign in · ${BRAND.name}`}</title>
      <LogoMark className="size-14" />
      <div className="space-y-3">
        <h1 className="text-4xl">Welcome to {BRAND.name}</h1>
        <p className="text-lg text-muted-foreground">Understand your medical case before your next doctor visit.</p>
      </div>
      <div className="w-full space-y-4">
        <GoogleSignInButton />
        <p className="text-sm text-muted-foreground">
          New here?{" "}
          <Link href="/signup" className="font-medium text-primary underline underline-offset-4">Create your space</Link>
        </p>
      </div>
    </div>
  );
}
