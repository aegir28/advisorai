"use client";

import { useState } from "react";
import { Check, Copy, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useDocuments, useTrace } from "@/features/case/hooks";
import { useTraceContext } from "@/features/trace/trace-context";
import type { ExternalSource, SourceRef, Trace, TraceNode } from "@/domain/types";
import { t, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { ErrorState, LoadingState } from "./states";
import { FlagMarker, KindTag, VerificationBadge, kindAccent } from "./markers";

/** Walk the trace tree once and collect what a person actually wants to see. */
function summarise(trace: Trace) {
  const sources: SourceRef[] = [];
  const findings: TraceNode[] = [];
  const checks: TraceNode[] = [];
  const references: ExternalSource[] = [];
  const seen = new Set<string>();

  const walk = (node: TraceNode, isRoot: boolean) => {
    if (node.source) {
      const key = `${node.source.docId}:${node.source.page}:${node.source.snippet}`;
      if (!seen.has(key)) {
        seen.add(key);
        sources.push(node.source);
      }
    }
    if (node.externalSource && !references.some((r) => r.id === node.externalSource!.id)) references.push(node.externalSource);
    if (!isRoot && node.level === "specialist" && !findings.some((f) => f.id === node.id)) findings.push(node);
    if (node.level === "verification" && !checks.some((c) => c.id === node.id)) checks.push(node);
    node.children.forEach((c) => walk(c, false));
  };
  walk(trace.root, false);
  return { sources, findings, checks, references };
}

export function TraceDrawer() {
  const { caseId, activeId, close } = useTraceContext();
  const trace = useTrace(caseId, activeId);
  const docs = useDocuments(caseId);
  const [copied, setCopied] = useState(false);

  const docName = (id: string) =>
    (docs.data?.find((d) => d.id === id)?.name ?? (id === "d_so" ? "Second-opinion note" : `Document ${id}`)).replace(/\.(pdf|jpe?g|png)$/i, "");

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable; the URL in the address bar is already the deep link */
    }
  };

  const data = trace.data;
  const s = data ? summarise(data) : null;

  return (
    <Sheet open={!!activeId} onOpenChange={(open) => !open && close()}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-md" data-no-print>
        <SheetHeader className="sticky top-0 z-10 border-b bg-popover p-5 pr-14">
          <SheetTitle className="font-heading text-xl">{t("report.whereFrom")}</SheetTitle>
          <SheetDescription>Every statement can be followed back to your own reports.</SheetDescription>
        </SheetHeader>

        <div className="space-y-8 p-5">
          {trace.status === "loading" && <LoadingState rows={2} />}
          {trace.status === "error" && <ErrorState onRetry={trace.reload} />}
          {trace.status === "success" && !data && (
            <ErrorState title="We couldn’t find that item" body="The link may be out of date. Close this panel and try another source." />
          )}

          {data && s && (
            <>
              <section aria-label="This statement" className="space-y-2">
                <p className="text-lg leading-relaxed">{data.root.text}</p>
                <div className="flex flex-wrap items-center gap-2">
                  {data.root.kind && <KindTag kind={data.root.kind} plain />}
                  {data.root.flag && <FlagMarker flag={data.root.flag} />}
                  {data.root.status && <VerificationBadge status={data.root.status} />}
                </div>
              </section>

              {s.sources.length > 0 && (
                <section aria-label="From your documents" className="space-y-3">
                  <h3 className="font-heading text-lg">From your documents</h3>
                  {s.sources.map((src) => <SourceCard key={`${src.docId}${src.page}${src.snippet}`} source={src} name={docName(src.docId)} />)}
                </section>
              )}

              {s.findings.length > 0 && (
                <section aria-label="Related findings" className="space-y-3">
                  <h3 className="font-heading text-lg">Related findings</h3>
                  <ul className="space-y-3">
                    {s.findings.slice(0, 4).map((f) => (
                      <li key={f.id} className="space-y-0.5">
                        <p className="text-xs text-muted-foreground">{f.label}</p>
                        <p className="leading-relaxed">{f.text}</p>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {(s.checks.length > 0 || s.references.length > 0) && (
                <section aria-label="How it was checked" className="space-y-3">
                  <h3 className="font-heading text-lg">How it was checked</h3>
                  <ul className="space-y-3">
                    {s.checks.map((c) => (
                      <li key={c.id} className="space-y-1.5">
                        <p className="leading-relaxed">{c.text}</p>
                        {c.status && (
                          <>
                            <VerificationBadge status={c.status} />
                            <p className="text-sm text-muted-foreground">{tk(`verify.${c.status}.long`)}</p>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                  {s.references.map((r) => (
                    <div key={r.id} className="rounded-2xl bg-evidence-soft/60 p-4 text-sm">
                      <p className="font-medium text-ink">{r.title}</p>
                      <p className="text-muted-foreground">{r.publisher} · {r.year}</p>
                      <p className="mt-2">“{r.snippet}”</p>
                    </div>
                  ))}
                </section>
              )}

              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Show the full trail</summary>
                <ol className="mt-4 space-y-3"><TraceNodeView node={data.root} docName={docName} top /></ol>
              </details>

              <div className="flex flex-wrap items-center gap-3 border-t pt-4">
                <Button variant="outline" size="sm" onClick={copyLink}>
                  {copied ? <Check aria-hidden data-icon="inline-start" /> : <Copy aria-hidden data-icon="inline-start" />}
                  {copied ? "Link copied" : "Copy link"}
                </Button>
                <span role="status" aria-live="polite" className="sr-only">{copied ? "Link copied to clipboard" : ""}</span>
                <span className="text-xs text-muted-foreground">Item {data.itemId}</span>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/** The original page, with the cited line highlighted. */
function SourceCard({ source, name }: { source: SourceRef; name: string }) {
  return (
    <figure className="overflow-hidden rounded-2xl border bg-white">
      <figcaption className="flex items-center gap-2 border-b bg-muted/50 px-3 py-2 text-sm">
        <FileText aria-hidden className="size-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-medium">{name}</span>
        <span className="shrink-0 text-muted-foreground">page {source.page}</span>
      </figcaption>
      <div aria-hidden className="space-y-1.5 px-4 pt-3">
        <div className="h-1.5 w-2/5 rounded bg-muted" />
        <div className="h-1.5 w-4/5 rounded bg-muted" />
      </div>
      <blockquote className="mx-4 my-2.5 rounded-lg border-l-4 border-primary bg-accent px-3 py-2.5 font-mono text-xs leading-relaxed text-ink">
        {source.snippet}
      </blockquote>
      {source.section && <p className="px-4 pb-3 text-xs text-muted-foreground">Section: {source.section}</p>}
    </figure>
  );
}

/** The complete trail, kept for people who want every step. */
function TraceNodeView({ node, docName, top }: { node: TraceNode; docName: (id: string) => string; top?: boolean }) {
  return (
    <li className="list-none">
      <div className={cn("rounded-xl border border-l-4 bg-card p-3", node.kind ? kindAccent(node.kind) : "border-l-border", top && "shadow-sm")}>
        <div className="mb-1 flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{node.label ?? node.level}</span>
          {node.status && <VerificationBadge status={node.status} />}
        </div>
        <p className="text-sm leading-relaxed">{node.text}</p>
        {node.source && <p className="mt-1.5 text-xs text-muted-foreground">{docName(node.source.docId)} · page {node.source.page}</p>}
      </div>
      {node.children.length > 0 && (
        <ol className="ml-3 mt-2 space-y-2 border-l-2 border-dashed pl-3">
          {node.children.map((child, i) => <TraceNodeView key={`${child.id}:${i}`} node={child} docName={docName} />)}
        </ol>
      )}
    </li>
  );
}
