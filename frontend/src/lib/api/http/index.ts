import type { AdvisorApi } from "../types";
import { ApiNotAvailableError, createHttpClient, type HttpClient } from "./client";
import { type Health, HealthSchema } from "./wire";

export { ApiError, ApiNotAvailableError, createHttpClient } from "./client";
export { fromWire, toWire } from "./casing";
export { decodeCase, decodeReport, decodeRun, decodeSpecialistReport, decodeTrace } from "./wire";

/** Every `AdvisorApi` method. A test keeps this in step with the interface and the mock. */
export const ADVISOR_API_METHODS = [
  "listCases",
  "getCase",
  "getCaseOverview",
  "createCase",
  "deleteCase",
  "safetyCheck",
  "getDocuments",
  "uploadDocument",
  "removeDocument",
  "startAnalysis",
  "getRun",
  "getTimeline",
  "getPerspectives",
  "getEvidence",
  "getCrossReview",
  "getSynthesis",
  "getReport",
  "getQuestions",
  "updateQuestion",
  "getTrace",
  "getSecondOpinion",
  "submitSecondOpinion",
  "getComparison",
] as const satisfies readonly (keyof AdvisorApi)[];

/**
 * The HTTP implementation of `AdvisorApi`. Phase 2A only builds the boundary (transport, error
 * envelope, request IDs, wire decoders): the backend serves just /health so far, so every
 * data method reports that it is not available yet. Phase 2B+ replaces each stub with a call
 * through `client.request` + the matching `decode*` function, with no screen changes.
 */
export function createHttpApi(): AdvisorApi {
  const stubs = Object.fromEntries(
    ADVISOR_API_METHODS.map((name) => [name, () => Promise.reject(new ApiNotAvailableError(name))]),
  );
  return stubs as unknown as AdvisorApi;
}

export async function fetchHealth(client: HttpClient): Promise<Health> {
  return HealthSchema.parse(await client.request("GET", "/health"));
}

export function defaultHttpClient(): HttpClient {
  return createHttpClient({ baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000" });
}
