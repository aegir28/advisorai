import { z } from "zod";
import {
  AnalysisRunSchema,
  CaseOverviewSchema,
  CaseSummarySchema,
  ComparisonSchema,
  CrossReviewDataSchema,
  DocumentItemSchema,
  EvidenceDataSchema,
  PatientReportSchema,
  PerspectivesDataSchema,
  QuestionSchema,
  SafetyCheckResultSchema,
  SecondOpinionStateSchema,
  StartAnalysisResultSchema,
  SynthesisSchema,
  TimelineDataSchema,
  TraceSchema,
} from "@/domain/schemas";
import type { AdvisorApi } from "./types";

/**
 * Runtime contract validation for the API boundary.
 *
 * ONE place declares which schema each `AdvisorApi` response must satisfy, and
 * ONE wrapper enforces it. Malformed data (from the mock today, from the real
 * backend tomorrow) throws a `ContractError` here and never reaches a screen;
 * the data hooks surface it as the normal error state.
 *
 * Methods that return nothing (`deleteCase`, `removeDocument`) have no schema.
 */

export class ContractError extends Error {
  constructor(
    readonly method: string,
    readonly detail: string,
  ) {
    super(`Response from ${method}() does not match its contract:\n${detail}`);
    this.name = "ContractError";
  }
}

type ResponseSchemas = { [K in keyof AdvisorApi]?: z.ZodType };

export const RESPONSE_SCHEMAS: ResponseSchemas = {
  listCases: z.array(CaseSummarySchema),
  getCase: CaseSummarySchema.nullable(),
  getCaseOverview: CaseOverviewSchema.nullable(),
  createCase: CaseSummarySchema,
  safetyCheck: SafetyCheckResultSchema,
  getDocuments: z.array(DocumentItemSchema),
  uploadDocument: DocumentItemSchema,
  startAnalysis: StartAnalysisResultSchema,
  getRun: AnalysisRunSchema.nullable(),
  getTimeline: TimelineDataSchema.nullable(),
  getPerspectives: PerspectivesDataSchema.nullable(),
  getEvidence: EvidenceDataSchema.nullable(),
  getCrossReview: CrossReviewDataSchema.nullable(),
  getSynthesis: SynthesisSchema.nullable(),
  getReport: PatientReportSchema.nullable(),
  getQuestions: z.array(QuestionSchema).nullable(),
  updateQuestion: QuestionSchema,
  getTrace: TraceSchema.nullable(),
  getSecondOpinion: SecondOpinionStateSchema,
  submitSecondOpinion: SecondOpinionStateSchema,
  getComparison: ComparisonSchema.nullable(),
};

/** Parse a value against a method's schema, or throw a `ContractError`. */
export function validateResponse<T>(method: string, schema: z.ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value);
  if (!result.success) throw new ContractError(method, z.prettifyError(result.error));
  return result.data;
}

/** Wrap any `AdvisorApi` so every response is validated before it is returned. */
export function withValidation(base: AdvisorApi): AdvisorApi {
  return new Proxy(base, {
    get(target, prop: string) {
      const key = prop as keyof AdvisorApi;
      const value = target[key];
      const schema = RESPONSE_SCHEMAS[key];
      if (typeof value !== "function" || !schema) return value;
      return async (...args: unknown[]) => {
        const raw = await (value as (...a: unknown[]) => Promise<unknown>).apply(target, args);
        return validateResponse(key, schema, raw);
      };
    },
  });
}
