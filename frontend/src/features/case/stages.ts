import type { MessageKey } from "@/i18n";

export interface CaseTab {
  key: string;
  label: MessageKey;
  /** Path under /cases/[caseId]. Empty string is the overview. */
  path: string;
}

/**
 * The whole case navigation: five places. Timeline, specialist perspectives,
 * evidence and "where information differs" are reached from inside Analysis
 * and the Report, never from here.
 */
export const CASE_TABS: CaseTab[] = [
  { key: "overview", label: "tab.overview", path: "" },
  { key: "analysis", label: "tab.analysis", path: "/analysis" },
  { key: "report", label: "tab.report", path: "/report" },
  { key: "questions", label: "tab.questions", path: "/questions" },
  { key: "second-opinion", label: "tab.secondOpinion", path: "/second-opinion" },
];

export function activeTabKey(pathname: string, caseId: string): string | null {
  const rest = pathname.replace(`/cases/${caseId}`, "");
  if (rest === "" || rest === "/") return "overview";
  const hit = CASE_TABS.find((t) => t.path && (rest === t.path || rest.startsWith(`${t.path}/`)));
  if (hit) return hit.key;
  if (rest.startsWith("/documents")) return "overview";
  return null;
}
