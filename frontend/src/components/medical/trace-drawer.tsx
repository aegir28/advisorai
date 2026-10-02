"use client";

import { useState } from "react";
import { Check, Copy, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useDocuments, useTrace } from "@/features/case/hooks";
import { useTraceContext } from "@/features/trace/trace-context";
import type { SourceRef, TraceNode } from "@/domain/types";
import { t, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { ErrorState, LoadingState } from "./states";
import { FlagMarker, KindTag, VerificationBadge, kindAccent } from "./markers";

export function TraceDrawer() {
  const { caseId, activeId, close } = useTraceContext();
  const trace = useTrace(caseId, activeId);
  const docs = useDocuments(caseId);
  const [copied, setCopied] = useState(false);

  const docName = (id: string) =>
    docs.data?.find((d) => d.id === id)?.name ?? (id === "d_so" ? "Second-opinion note" : `Document ${id}`);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable; the URL in the address bar is already the deep link */
    }
  };

  return (
    <Sheet open={!!activeId} onOpenChange={(open) => !open && close()}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-lg" data-no-print>
        <SheetHeader className="sticky top-0 z-10 border-b bg-popover p-5 pr-14">
          <SheetTitle className="font-heading text-xl">{t("report.whereFrom")}</SheetTitle>
          <SheetDescription>
            Every statement can be followed back to a page in your own records, or to the reference it relied on.
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-5 p-5">
          {trace.status === "loading" && <LoadingState rows={2} />}
          {trace.status === "error" && <ErrorState onRetry={trace.reload} />}
          {trace.status === "success" && !trace.data && (
            <ErrorState title="We couldn't find that item" body="The link may be out of date. Close this panel and try another source." />
          )}
          {trace.data && (
            <>
              <ol className="space-y-3">
                <TraceNodeView node={trace.data.root} docName={docName} top />
              </ol>
              <div className="flex flex-wrap items-center gap-2 border-t pt-4">
                <Button variant="outline" size="sm" onClick={copyLink}>
                  {copied ? <Check aria-hidden data-icon="inline-start" /> : <Copy aria-hidden data-icon="inline-start" />}
                  {copied ? "Link copied" : "Copy link to this source"}
                </Button>
                <span className="text-xs text-muted-foreground">Item {trace.data.itemId}</span>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function TraceNodeView({ node, docName, top }: { node: TraceNode; docName: (id: string) => string; top?: boolean }) {
  return (
    <li className="list-none">
      <div className={cn("rounded-xl border border-l-4 bg-card p-3.5", node.kind ? kindAccent(node.kind) : "border-l-border", top && "shadow-sm")}>
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
          <span className="eyebrow">{node.label ?? node.level}</span>
          {node.kind && <KindTag kind={node.kind} />}
          {node.flag && <FlagMarker flag={node.flag} />}
          {node.status && <VerificationBadge status={node.status} />}
        </div>
        <p className="text-sm leading-relaxed text-foreground">{node.text}</p>
        {node.status && node.level === "verification" && (
          <p className="mt-1.5 text-xs text-muted-foreground">{tk(`verify.${node.status}.long`)}</p>
        )}
        {node.source && <SourcePreview source={node.source} name={docName(node.source.docId)} />}
        {node.externalSource && (
          <div className="mt-2 rounded-lg border border-evidence/25 bg-evidence-soft/60 p-3 text-xs">
            <p className="font-medium text-ink">{node.externalSource.publisher}</p>
            <p className="text-muted-foreground">
              {node.externalSource.year} · {node.externalSource.section} · {node.externalSource.licence}
            </p>
            <blockquote className="mt-2 border-l-2 border-evidence/40 pl-2.5 text-foreground">{node.externalSource.snippet}</blockquote>
          </div>
        )}
      </div>
      {node.children.length > 0 && (
        <ol className="ml-3 mt-2 space-y-2 border-l-2 border-dashed border-border pl-3">
          {node.children.map((child) => (
            <TraceNodeView key={child.id} node={child} docName={docName} />
          ))}
        </ol>
      )}
    </li>
  );
}

/** A stylised preview of the original page with the cited line highlighted. */
function SourcePreview({ source, name }: { source: SourceRef; name: string }) {
  return (
    <figure className="mt-2.5 overflow-hidden rounded-lg border bg-white">
      <figcaption className="flex items-center gap-1.5 border-b bg-muted/60 px-2.5 py-1.5 text-xs text-muted-foreground">
        <FileText aria-hidden className="size-3.5 shrink-0" />
        <span className="truncate font-medium text-foreground">{name}</span>
        <span className="shrink-0">· page {source.page}</span>
        {source.section && <span className="hidden shrink-0 sm:inline">· {source.section}</span>}
      </figcaption>
      <div aria-hidden className="space-y-1.5 px-3 pt-3">
        <div className="h-1.5 w-2/5 rounded bg-muted" />
        <div className="h-1.5 w-4/5 rounded bg-muted" />
      </div>
      <blockquote className="mx-3 my-2 rounded border-l-4 border-primary bg-accent px-2.5 py-2 font-mono text-xs leading-relaxed text-ink">
        “{source.snippet}”
      </blockquote>
      <div aria-hidden className="space-y-1.5 px-3 pb-3">
        <div className="h-1.5 w-3/5 rounded bg-muted" />
        <div className="h-1.5 w-1/3 rounded bg-muted" />
      </div>
    </figure>
  );
}
