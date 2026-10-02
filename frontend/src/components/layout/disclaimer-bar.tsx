"use client";

import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EMERGENCY_NUMBERS } from "@/config/brand";
import { t } from "@/i18n";

/** Persistent safety disclaimer. Always visible, expandable for the full text. */
export function DisclaimerBar() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <div
        role="region"
        aria-label="Medical safety disclaimer"
        className="no-print fixed inset-x-0 bottom-0 z-40 border-t bg-card/95 px-3 py-2 text-xs text-muted-foreground backdrop-blur-sm"
      >
        <div className="mx-auto flex max-w-6xl items-center gap-2">
          <ShieldCheck aria-hidden className="size-4 shrink-0 text-primary" />
          <p className="line-clamp-2 flex-1 sm:line-clamp-1">{t("disclaimer.short")}</p>
          <Button variant="ghost" size="xs" onClick={() => setOpen(true)}>
            {t("disclaimer.learnMore")}
          </Button>
        </div>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">What this is, and what it is not</DialogTitle>
            <DialogDescription className="space-y-3 text-sm leading-relaxed text-foreground">
              <span className="block">{t("disclaimer.long")}</span>
              <span className="block">
                It never tells you to start, stop or change a medicine, never says a doctor is right or wrong, and never decides whether
                you should have a procedure.
              </span>
              <span className="block font-medium">
                If you have urgent symptoms, call {EMERGENCY_NUMBERS.join(" or ")} or go to the nearest emergency department.
              </span>
            </DialogDescription>
          </DialogHeader>
          <Button size="lg" onClick={() => setOpen(false)}>
            {t("common.close")}
          </Button>
        </DialogContent>
      </Dialog>
    </>
  );
}
