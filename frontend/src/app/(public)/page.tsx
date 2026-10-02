import Link from "next/link";
import { ArrowRight, Link2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { FlagMarker, KindTag } from "@/components/medical/markers";
import { BRAND } from "@/config/brand";
import { cn } from "@/lib/utils";

const STEPS = [
  { title: "Tell us what you need", body: "A few simple questions about what you want to understand." },
  { title: "Add your reports", body: "Upload what you have: reports, scans, prescriptions." },
  { title: "Get a clear summary", body: "A plain-language report, and the questions worth asking your doctor." },
];

/** A static miniature of the real report, used as the hero visual. */
function ReportPreview() {
  return (
    <div aria-hidden className="paper relative mx-auto w-full max-w-md space-y-5 p-6 shadow-xl">
      <p className="eyebrow">Your summary</p>
      <div className="space-y-1.5">
        <p className="leading-relaxed">Your angiography report describes about 80 % narrowing in one heart artery.</p>
        <div className="flex flex-wrap items-center gap-2">
          <KindTag kind="patient_fact" plain />
          <span className="inline-flex items-center gap-1 rounded-full border border-primary/25 bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground">
            <Link2 className="size-3" /> Source
          </span>
        </div>
      </div>
      <div className="space-y-1.5 rounded-2xl border border-dashed border-missing/50 bg-missing-soft/70 p-4">
        <FlagMarker flag="missing" />
        <p className="leading-relaxed">No heart ultrasound is in your reports. You may want to ask whether it has been done.</p>
      </div>
      <div className="rounded-2xl bg-secondary p-4">
        <p className="eyebrow mb-1">A question to ask</p>
        <p className="font-medium">Could an ultrasound change the decision or the timing?</p>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      <section className="mx-auto grid max-w-6xl items-center gap-14 px-5 pb-20 pt-14 sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:pb-28 lg:pt-24">
        <div className="space-y-8">
          <h1 className="text-5xl leading-[1.05] sm:text-6xl">{BRAND.tagline}</h1>
          <p className="max-w-xl text-xl text-muted-foreground">
            {BRAND.name} helps you understand your medical case before your next doctor visit. Add your reports, and we’ll prepare a clear
            summary and the questions worth asking.
          </p>
          <div className="space-y-3">
            <Link href="/signup" className={cn(buttonVariants({ size: "lg" }), "h-14 rounded-2xl px-8 text-base")}>
              Get started <ArrowRight aria-hidden data-icon="inline-end" />
            </Link>
            <p className="text-sm text-muted-foreground">
              Already have a space? <Link href="/login" className="font-medium text-primary underline underline-offset-4">Sign in</Link>
            </p>
          </div>
        </div>
        <ReportPreview />
      </section>

      <section id="how-it-works" className="border-y bg-card/60">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-6">
          <h2 className="mb-12 max-w-xl text-3xl sm:text-4xl">Simple on the surface. Careful underneath.</h2>
          <ol className="grid gap-10 sm:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="space-y-2">
                <p className="font-heading text-4xl text-primary/40">{i + 1}</p>
                <h3 className="text-xl">{s.title}</h3>
                <p className="text-muted-foreground">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="safety" className="mx-auto max-w-3xl space-y-6 px-5 py-20 text-center sm:px-6">
        <h2 className="text-3xl sm:text-4xl">Here to help you prepare. Not to replace your doctor.</h2>
        <p className="text-lg text-muted-foreground">
          {BRAND.name} doesn’t diagnose, prescribe, or tell you what to do. It shows you where things are clear, where they’re uncertain,
          and where they differ, so you can ask better questions.
        </p>
        <p className="text-muted-foreground">
          If you ever have urgent symptoms, such as chest pain right now or trouble breathing, please call 112 or 108 or go to the nearest
          emergency department. Don’t wait for an online tool.
        </p>
      </section>
    </>
  );
}
