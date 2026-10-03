"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ChevronLeft } from "lucide-react";
import { UrgentCareScreen } from "@/components/case/urgent-care-screen";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { BRAND } from "@/config/brand";
import type { SafetyCheckResult, Sex } from "@/domain/types";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";
import { readWizardStep, withWizardStep } from "@/lib/wizard-history";

const INTENTS = [
  "Understanding my diagnosis",
  "Understanding my treatment",
  "Preparing for a second opinion",
  "Understanding my reports",
  "Something else",
];

const RED_FLAGS = [
  { id: "chest_pain_now", label: "Chest pain happening right now" },
  { id: "stroke_signs", label: "Signs of a stroke: face drooping, slurred speech, sudden weakness" },
  { id: "breathless_rest", label: "Struggling to breathe, even at rest" },
  { id: "heavy_bleeding", label: "Heavy bleeding that won’t stop" },
  { id: "self_harm", label: "Thoughts of harming myself" },
];

/** Three short questions, one at a time. Never a form. */
export default function NewCasePage() {
  const router = useRouter();
  const ids = { story: useId(), age: useId(), err: useId() };
  const [step, setStep] = useState(0);
  const [intent, setIntent] = useState<string>("");
  const [story, setStory] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState<Sex>("F");
  const [flags, setFlags] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [urgent, setUrgent] = useState<SafetyCheckResult | null>(null);

  const LAST_STEP = 2;

  /** Every step is a history entry, so browser Back/Forward move between steps. */
  const goToStep = useCallback((n: number) => {
    window.history.pushState(withWizardStep(window.history.state, n), "");
    setStep(n);
  }, []);

  useEffect(() => {
    window.history.replaceState(withWizardStep(window.history.state, 0), "");
    const onPop = (e: PopStateEvent) => {
      const n = readWizardStep(e.state, LAST_STEP + 1);
      setError(null);
      setStep(Math.min(n, LAST_STEP));
      if (n <= LAST_STEP) setUrgent(null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  if (urgent) return <UrgentCareScreen result={urgent} />;

  const toggleFlag = (id: string, on: boolean) => setFlags((p) => (on ? [...p, id] : p.filter((f) => f !== id)));

  const next = () => {
    if (step === 1) {
      const ageNum = Number(age);
      if (story.trim().length < 8) return setError("Tell us a little more, in your own words. A sentence or two is plenty.");
      if (!Number.isFinite(ageNum) || ageNum < 1 || ageNum > 120) return setError("Please add your age (or the patient’s age).");
    }
    setError(null);
    goToStep(step + 1);
  };

  const finish = async (symptoms: string[] = flags) => {
    setBusy(true);
    setError(null);
    try {
      // The safety gate always runs BEFORE a case or analysis exists.
      const result = await api.safetyCheck({ text: story, currentSymptoms: symptoms });
      if (result.redFlag) {
        window.history.pushState(withWizardStep(window.history.state, LAST_STEP + 1), "");
        setUrgent(result);
        window.scrollTo({ top: 0 });
        return;
      }
      const created = await api.createCase({ intent: intent || "My case", concern: story.trim(), ageYears: Number(age), sex });
      router.push(`/cases/${created.id}/upload`);
    } catch {
      setError("We couldn’t save this. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl">
      <title>{`New case · ${BRAND.name}`}</title>
      <div className="mb-10 flex items-center justify-between">
        {step > 0 ? (
          <button type="button" onClick={() => { setError(null); window.history.back(); }} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ChevronLeft aria-hidden className="size-4" /> Back
          </button>
        ) : <span />}
        <p className="text-sm text-muted-foreground" aria-live="polite">Step {step + 1} of 3</p>
      </div>

      {step === 0 && (
        <section aria-labelledby="q0" className="space-y-8">
          <h1 id="q0" className="text-3xl sm:text-4xl">What would you like help understanding?</h1>
          <ul className="space-y-3">
            {INTENTS.map((label) => (
              <li key={label}>
                <button
                  type="button"
                  onClick={() => { setIntent(label); goToStep(1); }}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-2xl border bg-card px-5 py-4 text-left text-lg transition-colors hover:border-primary/50 hover:bg-accent/40",
                    intent === label && "border-primary bg-accent/50",
                  )}
                >
                  {label}
                  <ArrowRight aria-hidden className="size-5 text-muted-foreground" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {step === 1 && (
        <section aria-labelledby="q1" className="space-y-8">
          <h1 id="q1" className="text-3xl sm:text-4xl">What did your doctor tell you?</h1>
          <div className="space-y-2">
            <Label htmlFor={ids.story} className="sr-only">What did your doctor tell you?</Label>
            <Textarea
              id={ids.story} rows={5} value={story} onChange={(e) => setStory(e.target.value)} autoFocus
              placeholder="Write in your own words… for example, what was recommended, and what you’re unsure about."
              aria-describedby={error ? ids.err : undefined}
              className="min-h-40 rounded-2xl bg-card px-4 py-3 text-lg"
            />
          </div>
          <div className="flex flex-wrap items-end gap-x-8 gap-y-5">
            <div className="space-y-2">
              <Label htmlFor={ids.age}>Age</Label>
              <Input id={ids.age} type="number" inputMode="numeric" min={1} max={120} value={age} onChange={(e) => setAge(e.target.value)} placeholder="e.g. 52" className="w-28" />
            </div>
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-medium">Sex</legend>
              <div role="radiogroup" aria-label="Sex" className="flex gap-2">
                {([["F", "Female"], ["M", "Male"], ["X", "Other"]] as const).map(([v, label]) => (
                  <button
                    key={v} type="button" role="radio" aria-checked={sex === v} onClick={() => setSex(v)}
                    className={cn("rounded-full border px-4 py-2 text-sm font-medium transition-colors", sex === v ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-secondary")}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>
          <p className="text-sm text-muted-foreground">We use your age and sex only to understand your reports. Your name is never part of an analysis.</p>
          {error && <p id={ids.err} role="alert" className="text-sm font-medium text-destructive">{error}</p>}
          <Button size="lg" className="h-14 w-full rounded-2xl text-base sm:w-auto sm:px-8" onClick={next}>
            Continue <ArrowRight aria-hidden data-icon="inline-end" />
          </Button>
        </section>
      )}

      {step === 2 && (
        <section aria-labelledby="q2" className="space-y-8">
          <div className="space-y-3">
            <h1 id="q2" className="text-3xl sm:text-4xl">{t("gate.title")}</h1>
            <p className="text-lg text-muted-foreground">{t("gate.body")} Tick anything that is happening to you right now.</p>
          </div>
          <fieldset className="space-y-3">
            <legend className="sr-only">Symptoms happening right now</legend>
            {RED_FLAGS.map((o) => (
              <Label key={o.id} className="flex cursor-pointer items-start gap-3 rounded-2xl border bg-card p-4 text-base font-normal has-data-checked:border-urgent/50 has-data-checked:bg-urgent-soft">
                <Checkbox checked={flags.includes(o.id)} onCheckedChange={(v) => toggleFlag(o.id, v === true)} className="mt-1" />
                <span>{o.label}</span>
              </Label>
            ))}
          </fieldset>
          {error && <p role="alert" className="text-sm font-medium text-destructive">{error}</p>}
          <div className="space-y-3">
            <Button size="lg" className="h-14 w-full rounded-2xl text-base sm:w-auto sm:px-8" onClick={() => finish()} disabled={busy}>
              {busy ? "Checking…" : flags.length ? "Continue" : "None of these. Continue"} <ArrowRight aria-hidden data-icon="inline-end" />
            </Button>
            <div>
              <Button
                type="button" variant="ghost" size="sm" className="no-print text-muted-foreground"
                onClick={() => { setFlags(["chest_pain_now"]); void finish(["chest_pain_now"]); }}
              >
                Demo: show me the urgent-care screen
              </Button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
