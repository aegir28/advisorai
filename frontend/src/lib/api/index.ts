import { mockApi } from "@/mocks/mock-api";
import { invalidateQueries } from "../use-query";
import type { AdvisorApi } from "./types";
import { withValidation } from "./validate";

export type { AdvisorApi, SafetyCheckInput } from "./types";
export { ContractError } from "./validate";

const MUTATIONS: ReadonlySet<keyof AdvisorApi> = new Set([
  "createCase",
  "deleteCase",
  "uploadDocument",
  "removeDocument",
  "startAnalysis",
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
 * here (for example when NEXT_PUBLIC_API_MODE=http). No screen changes.
 *
 * Whichever implementation is used, every response is validated against the
 * contract schemas before it reaches the UI.
 */
export const api: AdvisorApi = withInvalidation(withValidation(mockApi));
