"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { PageHeader } from "@/components/layout/page-header";
import { useAuth } from "@/features/auth/auth-context";
import { readTextSize, saveTextSize, type TextSize } from "@/features/settings/preferences";
import { formatDate } from "@/lib/format";

const SIZES: { value: TextSize; label: string }[] = [
  { value: "normal", label: "Standard" },
  { value: "large", label: "Large" },
  { value: "xlarge", label: "Extra large" },
];

export default function ProfilePage() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [size, setSize] = useState<TextSize>("normal");
  // Read the stored preference after mount to avoid a hydration mismatch.
  useEffect(() => setSize(readTextSize()), []);

  const leave = () => {
    signOut();
    router.push("/");
  };

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
    <div className="space-y-12">
      <PageHeader title="Profile" />

      <section aria-labelledby="acct" className="space-y-4">
        <h2 id="acct" className="text-xl">Your account</h2>
        <div className="flex items-center gap-4">
          <span aria-hidden className="grid size-14 place-items-center rounded-full bg-secondary font-heading text-2xl text-secondary-foreground">
            {(user?.displayName ?? "D").slice(0, 1).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="font-medium">{user?.displayName}</p>
            <p className="truncate text-muted-foreground">{user?.email}</p>
            <p className="text-sm text-muted-foreground">Signed in with Google (simulated). Consent given {user?.consentedAt ? formatDate(user.consentedAt) : "—"}.</p>
          </div>
        </div>
        <p className="max-w-lg text-sm text-muted-foreground">
          Your name and email stay with your account. They are never part of an analysis, and cases are shown by name you chose, not by your identity.
        </p>
        <Button variant="outline" onClick={leave}>Sign out</Button>
      </section>

      <section aria-labelledby="read" className="space-y-4">
        <h2 id="read" className="text-xl">Reading comfort</h2>
        <RadioGroup
          value={size}
          onValueChange={(v) => { setSize(v as TextSize); saveTextSize(v as TextSize); }}
          className="flex flex-wrap gap-3"
          aria-label="Text size"
        >
          {SIZES.map((s) => (
            <label key={s.value} className="flex cursor-pointer items-center gap-2 rounded-full border px-4 py-2 has-data-checked:border-primary has-data-checked:bg-accent/50">
              <RadioGroupItem value={s.value} /> {s.label}
            </label>
          ))}
        </RadioGroup>
        <p className="text-sm text-muted-foreground">Language: English. Hindi and Hinglish can be added later without changing the screens.</p>
      </section>

      <section aria-labelledby="data" className="space-y-3">
        <h2 id="data" className="text-xl">Prototype data</h2>
        <p className="max-w-lg text-sm text-muted-foreground">
          Everything here lives only in this browser. Reset to remove cases you created, notes and sign-in, and bring back the three demo cases.
        </p>
        <Button variant="destructive" onClick={() => setConfirm(true)}>Reset prototype data</Button>
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
