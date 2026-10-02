"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import type { Question, QuestionAudience, QuestionStatus } from "@/domain/types";
import { tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./evidence-chip";

const STATUSES: QuestionStatus[] = ["not_asked", "partially_answered", "answered"];
const AUDIENCES: QuestionAudience[] = ["current_doctor", "second_opinion_doctor"];

export type QuestionPatch = { status?: QuestionStatus; note?: string };

function StatusControl({ question, onChange }: { question: Question; onChange: (patch: QuestionPatch) => void }) {
  return (
    <div role="radiogroup" aria-label={`Status: ${question.text}`} className="inline-flex flex-wrap gap-1.5">
      {STATUSES.map((s) => {
        const on = question.status === s;
        return (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange({ status: s })}
            className={cn(
              "flex items-center gap-1 rounded-full border px-3 py-1.5 text-sm transition-colors",
              on ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground",
            )}
          >
            {on && <Check aria-hidden className="size-3.5" />}
            {tk(`q.status.${s}`)}
          </button>
        );
      })}
    </div>
  );
}

/** One question: big readable text, a three-way tracker, details only on request. */
export function QuestionItem({ question, onChange, index, startHere }: { question: Question; onChange: (patch: QuestionPatch) => void; index: number; startHere?: boolean }) {
  const [copied, setCopied] = useState(false);
  const [why, setWhy] = useState(false);
  const [noteOpen, setNoteOpen] = useState(!!question.note);
  const [note, setNote] = useState(question.note ?? "");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(question.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <li className="space-y-4 py-7">
      <div className="flex items-start gap-4">
        <span aria-hidden className="mt-1 grid size-8 shrink-0 place-items-center rounded-full bg-secondary font-heading text-secondary-foreground">{index}</span>
        <div className="min-w-0 flex-1 space-y-1.5">
          {startHere && <p className="text-xs font-medium uppercase tracking-wide text-primary">Start here</p>}
          <p className={cn("text-xl leading-snug", question.status === "answered" && "text-muted-foreground")}>{question.text}</p>
        </div>
        <button type="button" onClick={copy} aria-label="Copy this question" data-no-print className="no-print mt-1 text-muted-foreground hover:text-foreground">
          {copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
        </button>
      </div>

      <div data-no-print className="no-print space-y-4 pl-12">
        <StatusControl question={question} onChange={onChange} />
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
          <button type="button" aria-expanded={why} onClick={() => setWhy((w) => !w)} className="text-primary underline-offset-4 hover:underline">
            {why ? "Hide why" : "Why this question?"}
          </button>
          <button type="button" aria-expanded={noteOpen} onClick={() => setNoteOpen((o) => !o)} className="text-primary underline-offset-4 hover:underline">
            {noteOpen ? "Hide note" : question.note ? "Your note" : "Add a note"}
          </button>
        </div>
        {why && (
          <div className="space-y-2 text-muted-foreground">
            <p>{question.trigger}</p>
            <div className="flex flex-wrap gap-2">
              {question.linkedItemIds.map((id) => <EvidenceChip key={id} itemId={id} />)}
            </div>
          </div>
        )}
        {noteOpen && (
          <Textarea
            aria-label="Your note about this question"
            placeholder="What did the doctor say? (saved only on this device in the prototype)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => note !== (question.note ?? "") && onChange({ note })}
            className="min-h-20 rounded-2xl bg-card px-3"
          />
        )}
      </div>
    </li>
  );
}

export function QuestionList({ questions, onChange }: { questions: Question[]; onChange: (id: string, patch: QuestionPatch) => void }) {
  const [audience, setAudience] = useState<QuestionAudience>("current_doctor");
  const list = questions.filter((q) => q.audience === audience).sort((a, b) => a.priority - b.priority);

  return (
    <div className="space-y-8">
      <div role="tablist" aria-label="Who are these questions for?" data-no-print className="no-print grid grid-cols-2 gap-1 rounded-2xl bg-muted p-1 sm:inline-grid">
        {AUDIENCES.map((a) => {
          const on = a === audience;
          const mine = questions.filter((q) => q.audience === a);
          return (
            <button
              key={a}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => setAudience(a)}
              className={cn("rounded-xl px-4 py-2.5 text-sm font-medium transition-colors sm:px-6", on ? "bg-card text-ink shadow-sm" : "text-muted-foreground hover:text-foreground")}
            >
              {tk(`q.audience.${a}`)}
              <span className="ml-1.5 text-xs text-muted-foreground">{mine.filter((q) => q.status === "answered").length}/{mine.length}</span>
            </button>
          );
        })}
      </div>
      <ol className="divide-y border-y" aria-label={tk(`q.audience.${audience}`)}>
        {list.map((q, i) => (
          <QuestionItem key={q.id} question={q} index={i + 1} startHere={i === 0 && q.priority === 1} onChange={(patch) => onChange(q.id, patch)} />
        ))}
      </ol>
    </div>
  );
}
