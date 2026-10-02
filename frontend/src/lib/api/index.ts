import { mockApi } from "@/mocks/mock-api";
import { invalidateQueries } from "../use-query";
import { createHttpApi } from "./http";
import type { AdvisorApi } from "./types";
import { withValidation } from "./validate";

export type { AdvisorApi, SafetyCheckInput } from "./types";
export { ContractError } from "./validate";
export { ApiError, ApiNotAvailableError } from "./http";

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
 *
 *   NEXT_PUBLIC_API_MODE unset (default) -> the in-browser mock (Phase 1 prototype)
 *   NEXT_PUBLIC_API_MODE=http            -> the HTTP boundary in ./http. Phase 2A builds the
 *                                           transport, error envelope and wire decoders only; data
 *                                           methods report "not available yet" until the backend
 *                                           serves them.
 *
 * Whichever implementation is used, every response is validated against the contract schemas
 * before it reaches the UI.
 */
const base: AdvisorApi = process.env.NEXT_PUBLIC_API_MODE === "http" ? createHttpApi() : mockApi;

export const api: AdvisorApi = withInvalidation(withValidation(base));
