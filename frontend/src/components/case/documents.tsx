"use client";

import { useId, useRef, useState } from "react";
import {
  CircleAlert,
  CircleCheck,
  Copy,
  File,
  FileImage,
  FileText,
  LoaderCircle,
  Trash2,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DocumentItem, DocumentStatus, DocumentType } from "@/domain/types";
import { formatSize } from "@/lib/format";
import { tk } from "@/i18n";
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
    if (!(ALLOWED.includes(f.type) || ALLOWED_EXT.test(f.name))) errors.push(`“${f.name}” isn't a PDF, JPG or PNG, so it was skipped.`);
    else if (f.size > MAX_FILE_MB * 1024 * 1024) errors.push(`“${f.name}” is larger than ${MAX_FILE_MB} MB, so it was skipped.`);
    else valid.push(f);
  }
  return { valid, errors };
}

export function UploadDropzone({ onFiles, busy }: { onFiles: (check: FileCheck) => void; busy?: boolean }) {
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
        "flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed bg-card px-6 py-10 text-center transition-colors",
        over ? "border-primary bg-accent" : "border-input",
      )}
    >
      <span className="grid size-12 place-items-center rounded-full bg-secondary text-secondary-foreground">
        <Upload aria-hidden className="size-6" />
      </span>
      <div className="space-y-1">
        <p className="font-medium">Drag your files here, or choose them</p>
        <p className="text-sm text-muted-foreground">PDF, JPG or PNG · up to {MAX_FILE_MB} MB each</p>
      </div>
      <input
        ref={inputRef} id={inputId} type="file" multiple accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
        className="sr-only" onChange={(e) => handle(e.target.files)}
      />
      <Button type="button" variant="outline" size="lg" disabled={busy} onClick={() => inputRef.current?.click()}>
        {busy ? "Adding…" : "Choose files"}
      </Button>
    </div>
  );
}

const typeIcon: Record<DocumentType, LucideIcon> = {
  lab: FileText, ecg: FileText, prescription: FileImage, discharge: FileText, imaging: FileImage, consult: FileText, other: File,
};

const statusStyle: Record<DocumentStatus, { icon: LucideIcon; cls: string; spin?: boolean }> = {
  ready: { icon: CircleCheck, cls: "text-evidence" },
  processing: { icon: LoaderCircle, cls: "text-fact", spin: true },
  needs_attention: { icon: CircleAlert, cls: "text-uncertain" },
  duplicate: { icon: Copy, cls: "text-muted-foreground" },
};

export function DocumentList({ documents, onRemove }: { documents: DocumentItem[]; onRemove?: (id: string) => void }) {
  return (
    <ul className="space-y-3">
      {documents.map((d) => {
        const Icon = typeIcon[d.type];
        const s = statusStyle[d.status];
        const SIcon = s.icon;
        return (
          <li key={d.id} className={cn("paper flex flex-wrap items-start gap-4 p-4", d.status === "needs_attention" && "border-uncertain/40", d.status === "duplicate" && "border-dashed")}>
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-secondary text-secondary-foreground">
              <Icon aria-hidden className="size-5" />
            </span>
            <div className="min-w-0 flex-1 space-y-1">
              <p className="break-words font-medium">{d.name}</p>
              <p className="text-xs text-muted-foreground">
                {d.pages} {d.pages === 1 ? "page" : "pages"} · {formatSize(d.sizeKb)}
                {d.ocrConfidence !== undefined && ` · reading confidence ${Math.round(d.ocrConfidence * 100)}%`}
              </p>
              <p className={cn("flex items-center gap-1.5 text-sm font-medium", s.cls)}>
                <SIcon aria-hidden className={cn("size-4", s.spin && "animate-spin motion-reduce:animate-none")} />
                {tk(`doc.${d.status}`)}
              </p>
              {d.note && <p className="text-sm text-muted-foreground">{d.note}</p>}
            </div>
            {onRemove && (
              <Button variant="ghost" size="icon" aria-label={`Remove ${d.name}`} onClick={() => onRemove(d.id)}>
                <Trash2 aria-hidden />
              </Button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
