"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Database, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/features/auth/auth-context";
import { formatDate } from "@/lib/format";

export default function ProfilePage() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);

  const resetPrototype = () => {
    try {
      window.localStorage.removeItem("advisorai.mock.v1");
    } catch {
      /* ignore */
    }
    signOut();
    router.push("/");
    setTimeout(() => window.location.reload(), 50);
  };

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <PageHeader eyebrow="Profile" title="Your profile" description="Only what’s needed to keep your cases private to you." />

      <section className="paper space-y-4 p-5" aria-labelledby="acct">
        <h2 id="acct" className="text-xl">Account</h2>
        <dl className="grid gap-4 sm:grid-cols-2">
          <div><dt className="eyebrow">Name shown here</dt><dd className="mt-1">{user?.displayName}</dd></div>
          <div><dt className="eyebrow">Email</dt><dd className="mt-1 break-all">{user?.email}</dd></div>
          <div className="sm:col-span-2">
            <dt className="eyebrow">Consent given</dt>
            <dd className="mt-1">{user ? formatDate(user.consentedAt) : "—"} · prototype use, fictional data only</dd>
          </div>
        </dl>
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
          Your name and email stay in your account. They are never placed in an analysis, and cases are shown by code.
        </p>
      </section>

      <section className="paper space-y-3 p-5" aria-labelledby="data">
        <h2 id="data" className="text-xl">Prototype data</h2>
        <p className="text-sm text-muted-foreground">
          Everything in this prototype lives only in this browser. Reset to remove cases you created, notes, and sign-in, and restore the three demo cases.
        </p>
        <Button variant="destructive" onClick={() => setConfirm(true)}>
          <Database aria-hidden data-icon="inline-start" /> Reset prototype data
        </Button>
      </section>

      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">Reset all prototype data?</DialogTitle>
            <DialogDescription>This clears your created cases, question notes and sign-in on this device. The demo cases come back.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(false)}>Cancel</Button>
            <Button variant="destructive" onClick={resetPrototype}>Reset everything</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
