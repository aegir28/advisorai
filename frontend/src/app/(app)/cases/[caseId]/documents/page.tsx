"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FolderOpen, Plus } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { DocumentList } from "@/components/case/documents";
import { EmptyState, ErrorState, LoadingState, PartialNotice } from "@/components/medical/states";
import { buttonVariants } from "@/components/ui/button";
import { useCase, useDocuments } from "@/features/case/hooks";
import { cn } from "@/lib/utils";

export default function DocumentsPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const c = useCase(caseId);
  const docs = useDocuments(caseId);

  if (docs.status === "loading") return <LoadingState rows={3} />;
  if (docs.status === "error") return <ErrorState onRetry={docs.reload} />;
  const documents = docs.data ?? [];
  const attention = documents.filter((d) => d.status === "needs_attention");
  const canAdd = c.data && c.data.status !== "complete" && c.data.status !== "partial";

  return (
    <>
      <PageHeader
        eyebrow="Documents"
        title="Your document library"
        description="Every document is classified, read and linked to the facts taken from it."
        actions={
          canAdd ? (
            <Link href={`/cases/${caseId}/upload`} className={cn(buttonVariants({ variant: "outline" }))}>
              <Plus aria-hidden data-icon="inline-start" /> Add records
            </Link>
          ) : undefined
        }
      />
      {attention.length > 0 && (
        <div className="mb-5">
          <PartialNotice title={`${attention.length} ${attention.length === 1 ? "document needs" : "documents need"} attention`}>
            We marked uncertain values rather than guessing. A clearer copy would make the analysis more complete.
          </PartialNotice>
        </div>
      )}
      {documents.length === 0 ? (
        <EmptyState icon={FolderOpen} title="No documents yet" body="Add your records to get started." action={{ label: "Add records", href: `/cases/${caseId}/upload` }} />
      ) : (
        <DocumentList documents={documents} />
      )}
    </>
  );
}
