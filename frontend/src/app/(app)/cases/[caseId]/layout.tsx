"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { CaseFrame } from "@/components/case/case-frame";
import { LoadingState } from "@/components/medical/states";
import { TraceProvider } from "@/features/trace/trace-context";

export default function CaseLayout({ children }: { children: React.ReactNode }) {
  const { caseId } = useParams<{ caseId: string }>();
  return (
    // useSearchParams (deep-linked evidence) needs a Suspense boundary.
    <Suspense fallback={<LoadingState rows={2} />}>
      <TraceProvider caseId={caseId}>
        <CaseFrame caseId={caseId}>{children}</CaseFrame>
      </TraceProvider>
    </Suspense>
  );
}
