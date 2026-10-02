import type { MessageKey } from "@/i18n";

export interface Stage {
  key: string;
  label: MessageKey;
  /** Path under /cases/[caseId]. Empty string is the overview. */
  path: string;
  group: "start" | "analysis" | "prepare" | "compare";
  /** True when the screen needs finished analysis results. */
  needsResults: boolean;
}

/** The whole journey, in order. Drives the stage nav and the next/back footer. */
export const STAGES: Stage[] = [
  { key: "overview", label: "stage.overview", path: "", group: "start", needsResults: false },
  { key: "documents", label: "stage.documents", path: "/documents", group: "start", needsResults: false },
  { key: "analysis", label: "stage.analysis", path: "/analysis", group: "analysis", needsResults: false },
  { key: "timeline", label: "stage.timeline", path: "/timeline", group: "analysis", needsResults: true },
  { key: "perspectives", label: "stage.perspectives", path: "/perspectives", group: "analysis", needsResults: true },
  { key: "evidence", label: "stage.evidence", path: "/evidence", group: "analysis", needsResults: true },
  { key: "review", label: "stage.review", path: "/review", group: "analysis", needsResults: true },
  { key: "synthesis", label: "stage.synthesis", path: "/synthesis", group: "analysis", needsResults: true },
  { key: "report", label: "stage.report", path: "/report", group: "prepare", needsResults: true },
  { key: "questions", label: "stage.questions", path: "/questions", group: "prepare", needsResults: true },
  { key: "second-opinion", label: "stage.secondOpinion", path: "/second-opinion", group: "compare", needsResults: true },
  { key: "comparison", label: "stage.comparison", path: "/comparison", group: "compare", needsResults: true },
];

export function stageIndexFor(pathname: string, caseId: string): number {
  const rest = pathname.replace(`/cases/${caseId}`, "");
  const exact = STAGES.findIndex((s) => s.path === rest);
  if (exact >= 0) return exact;
  // Upload lives under the "documents" stage.
  if (rest.startsWith("/upload")) return 1;
  return -1;
}
