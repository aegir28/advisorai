"use client";

import { useId, useRef, useState } from "react";
import { ChevronDown, FileText, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DocumentItem, DocumentStatus } from "@/domain/types";
import { formatSize } from "@/lib/format";
import { cn } from "@/lib/utils";

export const MAX_FILE_MB = 20;
const ALLOWED = ["application/pdf", "image/jpeg", "image/png"];
const ALLOWED_EXT = /\.(pdf|jpe?g|png)$/i;

export interface FileCheck {
  valid: File[];
  errors: string[];
}

/** Mirrors the blueprint's upload limits: PDF/JPG/PNG only, 20 MB per file. */
export function validateFiles(files: File[]): FileCheck {
  const valid: File[] = [];
  const errors: string[] = [];
  for (const f of files) {
    if (!(ALLOWED.includes(f.type) || ALLOWED_EXT.test(f.name))) errors.push(`“${f.name}” isn’t a PDF, JPG or PNG, so it was skipped.`);
    else if (f.size > MAX_FILE_MB * 1024 * 1024) errors.push(`“${f.name}” is larger than ${MAX_FILE_MB} MB, so it was skipped.`);
    else valid.push(f);
  }
  return { valid, errors };
}

export function UploadDropzone({ onFiles, busy, prompt = "Drop files here" }: { onFiles: (check: FileCheck) => void; busy?: boolean; prompt?: string }) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const handle = (list: FileList | null) => {
    if (list && list.length) onFiles(validateFiles(Array.from(list)));
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); handle(e.dataTransfer.files); }}
      className={cn(
        "flex flex-col items-center gap-4 rounded-3xl border-2 border-dashed px-6 py-12 text-center transition-colors",
        over ? "border-primary bg-accent" : "border-input bg-card/60",
      )}
    >
      <Upload aria-hidden className="size-7 text-primary" />
      <div className="space-y-1">
        <p className="text-xl font-heading text-ink">{prompt}</p>
        <p className="text-sm text-muted-foreground">PDF, JPG or PNG · Up to {MAX_FILE_MB} MB</p>
      </div>
      <input
        ref={inputRef} id={inputId} type="file" multiple accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
        className="sr-only" onChange={(e) => handle(e.target.files)}
      />
      <Button type="button" size="lg" className="rounded-2xl px-6" disabled={busy} onClick={() => inputRef.current?.click()}>
        {busy ? "Adding…" : "Choose files"}
      </Button>
    </div>
  );
}

/** Plain-language document status. */
export const docStatusText: Record<DocumentStatus, string> = {
  ready: "Ready ✓",
  processing: "Processing…",
  needs_attention: "Needs a clearer copy",
  duplicate: "Already added",
};

const docStatusCls: Record<DocumentStatus, string> = {
  ready: "text-primary",
  processing: "text-fact",
  needs_attention: "text-uncertain",
  duplicate: "text-muted-foreground",
};

/** Simple document rows. Technical details stay behind a disclosure. */
export function DocumentList({ documents, onRemove }: { documents: DocumentItem[]; onRemove?: (id: string) => void }) {
  return (
    <ul className="divide-y rounded-2xl border bg-card">
      {documents.map((d) => (
        <li key={d.id} className="flex items-start gap-2 px-4 py-3.5">
          <details className="group min-w-0 flex-1">
            <summary className="flex cursor-pointer list-none items-center gap-3">
              <FileText aria-hidden className="size-5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate font-medium">{d.name.replace(/\.(pdf|jpe?g|png)$/i, "")}</span>
              <span className={cn("shrink-0 text-sm", docStatusCls[d.status])}>{docStatusText[d.status]}</span>
              <ChevronDown aria-hidden className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
            </summary>
            <dl className="mt-3 space-y-1 pl-8 text-sm text-muted-foreground">
              <div className="flex gap-2"><dt>File</dt><dd className="break-all text-foreground">{d.name}</dd></div>
              <div className="flex gap-2"><dt>Size</dt><dd className="text-foreground">{d.pages} {d.pages === 1 ? "page" : "pages"} · {formatSize(d.sizeKb)}</dd></div>
              {d.ocrConfidence !== undefined && (
                <div className="flex gap-2"><dt>How clearly we could read it</dt><dd className="text-foreground">{Math.round(d.ocrConfidence * 100)}%</dd></div>
              )}
              {d.note && <p className="pt-1">{d.note}</p>}
            </dl>
          </details>
          {onRemove && (
            <Button variant="ghost" size="icon-sm" aria-label={`Remove ${d.name}`} onClick={() => onRemove(d.id)}>
              <Trash2 aria-hidden />
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}
