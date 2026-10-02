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
        title="This isn’t ready yet"
        body="This fills in once we’ve reviewed your reports. You can see where things stand on the Analysis page."
        action={{ label: "See progress", href: `/cases/${caseId}/analysis` }}
      />
    );
  }
  return <>{children(query.data)}</>;
}
