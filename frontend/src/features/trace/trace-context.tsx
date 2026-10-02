"use client";

import { createContext, useCallback, useContext, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { TraceDrawer } from "@/components/medical/trace-drawer";

/**
 * Global traceability. The open evidence item lives in the URL
 * (?evidence=<itemId>), so every source can be deep-linked, shared and
 * reached with the browser back button, from any case screen.
 */

export const EVIDENCE_PARAM = "evidence";

interface TraceContextValue {
  caseId: string;
  activeId: string | null;
  hrefFor: (itemId: string) => string;
  close: () => void;
}

const TraceContext = createContext<TraceContextValue | null>(null);

export function TraceProvider({ caseId, children }: { caseId: string; children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const activeId = params.get(EVIDENCE_PARAM);

  const hrefFor = useCallback(
    (itemId: string) => {
      const next = new URLSearchParams(params.toString());
      next.set(EVIDENCE_PARAM, itemId);
      return `${pathname}?${next.toString()}`;
    },
    [params, pathname],
  );

  const close = useCallback(() => {
    const next = new URLSearchParams(params.toString());
    next.delete(EVIDENCE_PARAM);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [params, pathname, router]);

  const value = useMemo(() => ({ caseId, activeId, hrefFor, close }), [caseId, activeId, hrefFor, close]);

  return (
    <TraceContext.Provider value={value}>
      {children}
      <TraceDrawer />
    </TraceContext.Provider>
  );
}

export function useTraceContext(): TraceContextValue {
  const ctx = useContext(TraceContext);
  if (!ctx) throw new Error("useTraceContext must be used inside <TraceProvider>");
  return ctx;
}
