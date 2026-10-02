import type { Metadata } from "next";
import { AuthForm } from "@/features/auth/auth-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <div className="mx-auto flex min-h-[70dvh] max-w-6xl items-center justify-center px-4 py-12">
      <AuthForm mode="login" />
    </div>
  );
}
