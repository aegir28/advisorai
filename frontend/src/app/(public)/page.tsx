import Link from "next/link";
import {
  ArrowRight,
  Ban,
  BookCheck,
  Check,
  FileUp,
  Layers,
  Link2,
  ListChecks,
  Scale,
  ScanSearch,
  Siren,
  Users,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { FlagMarker, KindTag } from "@/components/medical/markers";
import { BRAND } from "@/config/brand";
import { cn } from "@/lib/utils";

const STEPS = [
  { icon: FileUp, title: "Add your records", body: "Reports, prescriptions, scans, discharge notes. Safely sorted and read for you." },
  { icon: Layers, title: "Specialist perspectives", body: "Only the relevant specialist views look at your case, each through its own lens." },
  { icon: ScanSearch, title: "Every claim checked", body: "Statements are checked against your own documents and a curated reference library." },
  { icon: ListChecks, title: "A report and your questions", body: "A calm, plain-language report, plus questions made from your own gaps and conflicts." },
];

const PRINCIPLES = [
  { icon: Link2, title: "Every statement is traceable", body: "Tap “Source” on any sentence to see the page of your record it came from." },
  { icon: ScanSearch, title: "Uncertainty stays visible", body: "When the records can’t settle something, we say so, with the reason." },
  { icon: Scale, title: "Disagreement is shown, not smoothed over", body: "Where perspectives differ, you see both sides. We never count votes or pick a winner." },
  { icon: Users, title: "Built for the conversation", body: "The output is a list of prioritised questions you can tick off during a visit." },
];

const DOES = [
  "Explains what your records contain",
  "Highlights what is important and what is missing",
  "Shows where uncertainty or different views exist",
  "Writes personalised, prioritised questions",
  "Compares a later second opinion side by side",
];
const DOES_NOT = [
  "Diagnose, or replace your doctor",
  "Prescribe, or tell you to stop a medicine",
  "Say a doctor is right or wrong",
  "Decide whether you should have a procedure",
  "Make any treatment decision for you",
];

/** A static miniature of the real report, used as the hero visual. */
function ReportPreview() {
  return (
    <div aria-hidden className="paper relative mx-auto w-full max-w-md space-y-4 p-5 shadow-xl sm:p-6">
      <div className="flex items-center justify-between">
        <p className="eyebrow">Your preparation report</p>
        <span className="rounded-full bg-muted px-2 py-0.5 text-[0.7rem] text-muted-foreground">Fictional case</span>
      </div>
      <div className="space-y-1.5 border-l-4 border-l-fact pl-3">
        <p className="text-sm leading-relaxed">Your angiography report describes about 80 % narrowing in one heart artery.</p>
        <div className="flex flex-wrap items-center gap-1.5">
          <KindTag kind="patient_fact" />
          <span className="inline-flex items-center gap-1 rounded-full border border-primary/25 bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground">
            <Link2 className="size-3" /> Source · page 2
          </span>
        </div>
      </div>
      <div className="space-y-1.5 rounded-xl border border-dashed border-missing/50 bg-missing-soft/70 p-3">
        <FlagMarker flag="missing" />
        <p className="text-sm leading-relaxed">No heart ultrasound (echocardiogram) is in your records. You may want to ask whether it has been done.</p>
      </div>
      <div className="space-y-1.5 rounded-xl border border-disagree/30 bg-disagree-soft/60 p-3">
        <FlagMarker flag="disagreement" />
        <p className="text-sm leading-relaxed">Perspectives differ on timing. Both views are kept, and none is picked for you.</p>
      </div>
      <div className="rounded-xl bg-secondary p-3">
        <p className="eyebrow mb-1">Ask your doctor · most important</p>
        <p className="text-sm font-medium">Could an echocardiogram change the decision or the timing?</p>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      {/* Hero */}
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-16 pt-12 sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:pb-24 lg:pt-20">
        <div className="space-y-7">
          <p className="eyebrow">Second-opinion preparation</p>
          <h1 className="text-4xl leading-[1.08] sm:text-5xl lg:text-6xl">{BRAND.tagline}</h1>
          <p className="max-w-xl text-lg text-muted-foreground">
            {BRAND.name} reads your medical records, looks at them from several specialist views, checks every claim against evidence, and
            hands you a calm report and the questions worth asking. You walk into your next appointment prepared, not diagnosed.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/signup" className={cn(buttonVariants({ size: "lg" }))}>
              Get started <ArrowRight aria-hidden data-icon="inline-end" />
            </Link>
            <Link href="/login" className={cn(buttonVariants({ size: "lg", variant: "outline" }))}>
              Explore the demo cases
            </Link>
          </div>
          <p className="max-w-lg text-sm text-muted-foreground">
            Prototype on fictional data only. Please don’t upload real medical information.
          </p>
        </div>
        <ReportPreview />
      </section>

      {/* Does / does not */}
      <section className="border-y bg-card/60">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-14 sm:px-6 md:grid-cols-2">
          <div className="paper p-6">
            <h2 className="mb-4 text-2xl">{BRAND.name} does</h2>
            <ul className="space-y-3">
              {DOES.map((d) => (
                <li key={d} className="flex gap-3">
                  <Check aria-hidden className="mt-1 size-4 shrink-0 text-primary" />
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="paper p-6">
            <h2 className="mb-4 text-2xl">{BRAND.name} does not</h2>
            <ul className="space-y-3">
              {DOES_NOT.map((d) => (
                <li key={d} className="flex gap-3 text-muted-foreground">
                  <Ban aria-hidden className="mt-1 size-4 shrink-0" />
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="mb-10 max-w-2xl space-y-3">
          <p className="eyebrow">How it works</p>
          <h2 className="text-3xl sm:text-4xl">The complexity stays behind the scenes. You see four calm steps.</h2>
        </div>
        <ol className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="paper flex flex-col gap-3 p-5">
              <div className="flex items-center justify-between">
                <span className="grid size-10 place-items-center rounded-xl bg-secondary text-secondary-foreground">
                  <s.icon aria-hidden className="size-5" />
                </span>
                <span className="font-heading text-2xl text-muted-foreground/60">{i + 1}</span>
              </div>
              <h3 className="text-lg">{s.title}</h3>
              <p className="text-sm text-muted-foreground">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Principles */}
      <section className="bg-primary text-primary-foreground">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="mb-10 max-w-2xl text-3xl text-primary-foreground sm:text-4xl">Accuracy comes from architecture and verification, not from a confident tone.</h2>
          <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2">
            {PRINCIPLES.map((p) => (
              <div key={p.title} className="flex gap-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary-foreground/10">
                  <p.icon aria-hidden className="size-5" />
                </span>
                <div>
                  <h3 className="mb-1 text-lg text-primary-foreground">{p.title}</h3>
                  <p className="text-primary-foreground/80">{p.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Safety */}
      <section id="safety" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="paper grid gap-6 p-6 sm:p-8 md:grid-cols-[auto_1fr] md:items-center">
          <span className="grid size-14 place-items-center rounded-2xl bg-urgent-soft text-urgent">
            <Siren aria-hidden className="size-7" />
          </span>
          <div className="space-y-2">
            <h2 className="text-2xl">Urgent symptoms never wait for a tool</h2>
            <p className="text-muted-foreground">
              Before any analysis starts, we check for symptoms such as chest pain right now, stroke signs, breathlessness at rest, heavy
              bleeding or thoughts of self-harm. If any are present we stop, and point you to emergency care instead.
            </p>
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <BookCheck aria-hidden className="size-4 shrink-0" /> Emergency wording must be clinician-reviewed before any real-user launch.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
