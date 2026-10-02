"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FolderOpen } from "lucide-react";
import { DocumentList } from "@/components/case/documents";
import { PageIntro } from "@/components/layout/page-intro";
import { EmptyState, ErrorState, LoadingState, PartialNotice } from "@/components/medical/states";
import { useDocuments } from "@/features/case/hooks";

export default function DocumentsPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const docs = useDocuments(caseId);

  if (docs.status === "loading") return <LoadingState rows={2} />;
  if (docs.status === "error") return <ErrorState onRetry={docs.reload} />;
  const documents = docs.data ?? [];
  const attention = documents.filter((d) => d.status === "needs_attention");

  return (
    <>
      <PageIntro title="Your reports">The documents your case is based on.</PageIntro>
      {attention.length > 0 && (
        <div className="mb-6">
          <PartialNotice title={`${attention.length} ${attention.length === 1 ? "report needs" : "reports need"} a clearer copy`}>
            We marked anything uncertain rather than guessing. A clearer copy would make your summary more complete.
          </PartialNotice>
        </div>
      )}
      {documents.length === 0 ? (
        <EmptyState icon={FolderOpen} title="No reports yet" body="Add your reports to get started." action={{ label: "Add reports", href: `/cases/${caseId}/upload` }} />
      ) : (
        <DocumentList documents={documents} />
      )}
      <p className="mt-6 text-sm">
        <Link href={`/cases/${caseId}`} className="text-primary underline underline-offset-4">Back to overview</Link>
      </p>
    </>
  );
}
