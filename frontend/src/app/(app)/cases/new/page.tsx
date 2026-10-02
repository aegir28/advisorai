"use client";

import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldCheck, Siren } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { UrgentCareScreen } from "@/components/case/urgent-care-screen";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import type { SafetyCheckResult, Sex } from "@/domain/types";
import { api } from "@/lib/api";
import { t } from "@/i18n";

const RED_FLAG_OPTIONS = [
  { id: "chest_pain_now", label: "Chest pain happening right now" },
  { id: "stroke_signs", label: "Signs of a stroke (face drooping, slurred speech, sudden weakness)" },
  { id: "breathless_rest", label: "Struggling to breathe, even at rest" },
  { id: "heavy_bleeding", label: "Heavy bleeding that won't stop" },
  { id: "self_harm", label: "Thoughts of harming myself" },
];

export default function NewCasePage() {
  const router = useRouter();
  const ids = { concern: useId(), treatment: useId(), age: useId(), err: useId() };
  const [concern, setConcern] = useState("");
  const [treatment, setTreatment] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState<Sex>("F");
  const [flags, setFlags] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [urgent, setUrgent] = useState<SafetyCheckResult | null>(null);

  const toggleFlag = (id: string, on: boolean) => setFlags((prev) => (on ? [...prev, id] : prev.filter((f) => f !== id)));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ageNum = Number(age);
    if (concern.trim().length < 8) return setError("Please describe your main question in a sentence or two.");
    if (!Number.isFinite(ageNum) || ageNum < 1 || ageNum > 120) return setError("Please enter an age between 1 and 120.");
    setError(null);
    setBusy(true);
    try {
      // The safety gate always runs BEFORE a case or analysis exists.
      const result = await api.safetyCheck({ text: `${concern} ${treatment}`, currentSymptoms: flags });
      if (result.redFlag) {
        setUrgent(result);
        window.scrollTo({ top: 0 });
        return;
      }
      const created = await api.createCase({ concern: concern.trim(), proposedTreatment: treatment.trim() || undefined, ageYears: ageNum, sex });
      router.push(`/cases/${created.id}/upload`);
    } catch {
      setError("We couldn't save this case. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  if (urgent) return <UrgentCareScreen result={urgent} />;

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        eyebrow="New case · step 1 of 3"
        title="What would you like to prepare for?"
        description="Tell us your main question. Next you'll add your records, then we'll analyse them."
      />

      <form onSubmit={submit} noValidate className="space-y-8">
        <section className="paper space-y-5 p-5 sm:p-6" aria-labelledby="about-heading">
          <h2 id="about-heading" className="text-xl">About your case</h2>
          <div className="space-y-2">
            <Label htmlFor={ids.concern}>Your main question or concern</Label>
            <Textarea
              id={ids.concern} rows={3} value={concern} onChange={(e) => setConcern(e.target.value)}
              placeholder="For example: Is this procedure necessary now, or are there other options to ask about?"
              aria-describedby={error ? ids.err : undefined} className="min-h-24 bg-card px-3"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={ids.treatment}>
              Treatment or procedure being proposed <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Input id={ids.treatment} value={treatment} onChange={(e) => setTreatment(e.target.value)} placeholder="For example: angioplasty, knee arthroscopy" />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor={ids.age}>Age</Label>
              <Input id={ids.age} type="number" inputMode="numeric" min={1} max={120} value={age} onChange={(e) => setAge(e.target.value)} placeholder="e.g. 52" />
            </div>
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-medium">Sex</legend>
              <RadioGroup value={sex} onValueChange={(v) => setSex(v as Sex)} className="flex flex-wrap gap-4" aria-label="Sex">
                {([["F", "Female"], ["M", "Male"], ["X", "Other"]] as const).map(([v, label]) => (
                  <Label key={v} className="flex cursor-pointer items-center gap-2 font-normal">
                    <RadioGroupItem value={v} /> {label}
                  </Label>
                ))}
              </RadioGroup>
            </fieldset>
          </div>
          <p className="text-xs text-muted-foreground">
            Only age and sex are used to understand your records. Your name is never part of an analysis, and cases show a code, not a name.
          </p>
        </section>

        <section className="paper space-y-4 border-urgent/20 p-5 sm:p-6" aria-labelledby="gate-heading">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-urgent-soft text-urgent">
              <Siren aria-hidden className="size-5" />
            </span>
            <div>
              <h2 id="gate-heading" className="text-xl">{t("gate.title")}</h2>
              <p className="text-sm text-muted-foreground">{t("gate.body")}</p>
            </div>
          </div>
          <fieldset className="space-y-3">
            <legend className="sr-only">Symptoms happening right now</legend>
            {RED_FLAG_OPTIONS.map((o) => (
              <Label key={o.id} className="flex cursor-pointer items-start gap-3 rounded-xl border p-3 font-normal has-data-checked:border-urgent/40 has-data-checked:bg-urgent-soft">
                <Checkbox checked={flags.includes(o.id)} onCheckedChange={(v) => toggleFlag(o.id, v === true)} className="mt-0.5" />
                <span>{o.label}</span>
              </Label>
            ))}
          </fieldset>
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <ShieldCheck aria-hidden className="size-4 shrink-0 text-primary" />
            Nothing here? You can leave these empty. We also scan your description for the same warning signs.
          </p>
          <Button
            type="button" variant="ghost" size="sm" className="no-print"
            onClick={() => { setConcern("I have crushing chest pain right now"); setFlags(["chest_pain_now"]); if (!age) setAge("52"); }}
          >
            Demo: show me the urgent-care screen
          </Button>
        </section>

        {error && <p id={ids.err} role="alert" className="text-sm font-medium text-destructive">{error}</p>}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">Next: add your records.</p>
          <Button type="submit" size="lg" disabled={busy}>
            {busy ? "Checking…" : "Check and continue"} <ArrowRight aria-hidden data-icon="inline-end" />
          </Button>
        </div>
      </form>
    </div>
  );
}
