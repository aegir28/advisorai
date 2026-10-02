"use client";

import { useState } from "react";
import { Check, Copy, MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
    <div role="radiogroup" aria-label={`Status of question: ${question.text}`} className="inline-flex flex-wrap gap-1 rounded-full bg-muted p-1">
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
              "flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              on ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-card",
            )}
          >
            {on && <Check aria-hidden className="size-3" />}
            {tk(`q.status.${s}`)}
          </button>
        );
      })}
    </div>
  );
}

export function QuestionItem({ question, onChange, index }: { question: Question; onChange: (patch: QuestionPatch) => void; index: number }) {
  const [copied, setCopied] = useState(false);
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
    <li className={cn("paper space-y-4 p-4 sm:p-5", question.status === "answered" && "bg-muted/40")}>
      <div className="flex items-start gap-3">
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-secondary font-heading text-secondary-foreground">{index}</span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{question.category}</p>
          <p className={cn("text-lg leading-snug", question.status === "answered" && "text-muted-foreground")}>{question.text}</p>
        </div>
        <Button variant="ghost" size="icon" aria-label="Copy this question" onClick={copy} data-no-print>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        </Button>
      </div>

      <details className="rounded-xl bg-muted/50 px-3 py-2 text-sm">
        <summary className="cursor-pointer list-none font-medium">Why this question?</summary>
        <div className="mt-2 space-y-2">
          <p className="text-muted-foreground">{question.trigger}</p>
          <div className="flex flex-wrap gap-2">
            {question.linkedItemIds.map((id) => <EvidenceChip key={id} itemId={id} label={`Trigger · ${id}`} />)}
          </div>
        </div>
      </details>

      <div data-no-print className="no-print flex flex-wrap items-center justify-between gap-3">
        <StatusControl question={question} onChange={onChange} />
        <Button variant="ghost" size="sm" onClick={() => setNoteOpen((o) => !o)}>
          <MessageSquarePlus aria-hidden data-icon="inline-start" /> {noteOpen ? "Hide note" : "Add a note"}
        </Button>
      </div>
      {noteOpen && (
        <Textarea
          aria-label="Your note about this question"
          placeholder="What did the doctor say? (saved on your device only in this prototype)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => note !== (question.note ?? "") && onChange({ note })}
          className="min-h-20 bg-card px-3"
        />
      )}
      {question.note && !noteOpen && <p className="rounded-lg bg-secondary/60 px-3 py-2 text-sm">Your note: {question.note}</p>}
    </li>
  );
}

export function QuestionList({ questions, onChange }: { questions: Question[]; onChange: (id: string, patch: QuestionPatch) => void }) {
  return (
    <Tabs defaultValue="current_doctor" className="gap-5">
      <TabsList className="h-auto w-full flex-wrap justify-start gap-1 sm:w-auto" data-no-print>
        {AUDIENCES.map((a) => {
          const list = questions.filter((q) => q.audience === a);
          const answered = list.filter((q) => q.status === "answered").length;
          return (
            <TabsTrigger key={a} value={a} className="h-auto px-4 py-2">
              {tk(`q.audience.${a}`)}
              <span className="ml-1.5 text-xs text-muted-foreground">{answered}/{list.length}</span>
            </TabsTrigger>
          );
        })}
      </TabsList>
      {AUDIENCES.map((a) => {
        const list = questions.filter((q) => q.audience === a);
        let n = 0;
        return (
          <TabsContent key={a} value={a} className="space-y-8">
            {([1, 2, 3] as const).map((p) => {
              const group = list.filter((q) => q.priority === p);
              if (!group.length) return null;
              return (
                <section key={p} aria-labelledby={`prio-${a}-${p}`} className="space-y-3">
                  <h2 id={`prio-${a}-${p}`} className="flex items-center gap-2 text-lg">
                    <span className="rounded-full bg-primary px-2.5 py-0.5 text-xs font-medium text-primary-foreground">P{p}</span>
                    {tk(`q.priority.${p}`)}
                  </h2>
                  <ol className="space-y-3">
                    {group.map((q) => <QuestionItem key={q.id} question={q} index={++n} onChange={(patch) => onChange(q.id, patch)} />)}
                  </ol>
                </section>
              );
            })}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}
