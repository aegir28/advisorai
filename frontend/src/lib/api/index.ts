import { mockApi } from "@/mocks/mock-api";
import { invalidateQueries } from "../use-query";
import type { AdvisorApi } from "./types";

export type { AdvisorApi, SafetyCheckInput, StartAnalysisOptions } from "./types";

const MUTATIONS: ReadonlySet<keyof AdvisorApi> = new Set([
  "createCase",
  "deleteCase",
  "uploadDocument",
  "attachSampleRecords",
  "removeDocument",
  "startAnalysis",
  "skipToResults",
  "updateQuestion",
  "submitSecondOpinion",
]);

/** After any mutation, refresh active queries so every screen stays in sync. */
function withInvalidation(base: AdvisorApi): AdvisorApi {
  return new Proxy(base, {
    get(target, prop: string) {
      const key = prop as keyof AdvisorApi;
      const value = target[key];
      if (typeof value !== "function" || !MUTATIONS.has(key)) return value;
      return async (...args: unknown[]) => {
        const result = await (value as (...a: unknown[]) => Promise<unknown>).apply(target, args);
        invalidateQueries();
        return result;
      };
    },
  });
}

/**
 * The single place that decides which implementation the UI talks to.
 * Phase 1 uses the in-browser mock. When the FastAPI backend exists, an
 * `httpApi` implementing the same `AdvisorApi` interface replaces `mockApi`
 * here (for example behind a NEXT_PUBLIC_API_BASE_URL switch). No screen changes.
 */
export const api: AdvisorApi = withInvalidation(mockApi);
