"use client";

import { useEffect, useState } from "react";
import { Languages, Type } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { readTextSize, saveTextSize, type TextSize } from "@/features/settings/preferences";
import { BRAND } from "@/config/brand";

const SIZES: { value: TextSize; label: string; sample: string }[] = [
  { value: "normal", label: "Standard", sample: "16 px" },
  { value: "large", label: "Large", sample: "18 px" },
  { value: "xlarge", label: "Extra large", sample: "20 px" },
];

export default function SettingsPage() {
  const [size, setSize] = useState<TextSize>("normal");
  // Read the stored preference after mount to avoid a hydration mismatch.
  useEffect(() => setSize(readTextSize()), []);

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <PageHeader eyebrow="Settings" title="Reading preferences" description={`Make ${BRAND.name} comfortable to read. These stay on this device.`} />

      <section className="paper space-y-4 p-5" aria-labelledby="ts">
        <h2 id="ts" className="flex items-center gap-2 text-xl"><Type aria-hidden className="size-5 text-primary" /> Text size</h2>
        <RadioGroup
          value={size}
          onValueChange={(v) => { setSize(v as TextSize); saveTextSize(v as TextSize); }}
          className="grid gap-3 sm:grid-cols-3"
          aria-label="Text size"
        >
          {SIZES.map((s) => (
            <label key={s.value} className="flex cursor-pointer items-center gap-3 rounded-xl border bg-card p-3.5 has-data-checked:border-primary has-data-checked:bg-accent/50">
              <RadioGroupItem value={s.value} />
              <span><span className="block font-medium">{s.label}</span><span className="text-xs text-muted-foreground">{s.sample}</span></span>
            </label>
          ))}
        </RadioGroup>
      </section>

      <section className="paper space-y-3 p-5" aria-labelledby="lang">
        <h2 id="lang" className="flex items-center gap-2 text-xl"><Languages aria-hidden className="size-5 text-primary" /> Language</h2>
        <p className="text-sm text-muted-foreground">
          English for now. All text is stored in a message catalogue, so Hindi and Hinglish reports can be added later without redesigning the screens.
        </p>
        <p className="inline-block rounded-full border bg-muted px-3 py-1 text-sm">English (current)</p>
      </section>
    </div>
  );
}
