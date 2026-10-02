import type { Metadata } from "next";
import { AuthForm } from "@/features/auth/auth-form";

export const metadata: Metadata = { title: "Get started" };

export default function SignupPage() {
  return (
    <div className="mx-auto flex min-h-[70dvh] max-w-6xl items-center justify-center px-4 py-12">
      <AuthForm mode="signup" />
    </div>
  );
}
