"use client";

import { FileSearch } from "lucide-react";
import { EmptyState, ErrorState, LoadingState } from "@/components/medical/states";
import type { QueryResult } from "@/lib/use-query";

/**
 * Wraps every results screen: loading, error and "not ready yet" are handled
 * once, consistently. A `null` result means the analysis hasn't produced data.
 */
export function ResultsGate<T>({
  query,
  caseId,
  children,
}: {
  query: QueryResult<T | null>;
  caseId: string;
  children: (data: T) => React.ReactNode;
}) {
  if (query.status === "loading") return <LoadingState rows={3} />;
  if (query.status === "error") return <ErrorState onRetry={query.reload} />;
  if (!query.data) {
    return (
      <EmptyState
        icon={FileSearch}
        title="Results aren't ready yet"
        body="This screen fills in once your records have been analysed. Check the analysis page to see where things stand."
        action={{ label: "Go to analysis", href: `/cases/${caseId}/analysis` }}
      />
    );
  }
  return <>{children(query.data)}</>;
}
