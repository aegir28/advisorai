import { z } from "zod";
import {
  AnalysisRunSchema,
  CaseV1Schema,
  PatientReportSchema,
  SpecialistReportSchema,
  TraceSchema,
} from "@/domain/schemas";
import type { AnalysisRun, CaseV1, PatientReport, SpecialistReport, Trace } from "@/domain/types";
import { fromWire } from "./casing";

/**
 * Decoders for the five versioned wire contracts:
 *
 *   backend (snake_case JSON, validated by Pydantic)
 *     -> fromWire (explicit key table)
 *     -> Zod schema (rejects anything the backend should not have sent)
 *     -> frontend domain model
 *
 * A decode failure throws a ZodError; `withValidation` and the data hooks turn that into the normal
 * error state, exactly as for the mock.
 */
export const decodeCase = (wire: unknown): CaseV1 => CaseV1Schema.parse(fromWire(wire, "case.v1"));
export const decodeSpecialistReport = (wire: unknown): SpecialistReport => SpecialistReportSchema.parse(fromWire(wire, "specialist_report.v1"));
export const decodeReport = (wire: unknown): PatientReport => PatientReportSchema.parse(fromWire(wire, "report.v1"));
export const decodeTrace = (wire: unknown): Trace => TraceSchema.parse(fromWire(wire, "trace.v1"));
export const decodeRun = (wire: unknown): AnalysisRun => AnalysisRunSchema.parse(fromWire(wire, "run.v1"));

/** GET /api/v1/health */
export const HealthSchema = z.object({
  status: z.literal("ok"),
  service: z.string(),
  version: z.string(),
  environment: z.string(),
});
export type Health = z.infer<typeof HealthSchema>;
