import { z } from "zod";
import {
  CaseSummarySchema,
  CaseStatusSchema,
  DocumentItemSchema,
  DocumentStatusSchema,
  DocumentTypeSchema,
  SafetyCheckResultSchema,
  SexSchema,
} from "@/domain/schemas";
import type { CaseSummary, DocumentItem, NewCaseInput, SafetyCheckResult } from "@/domain/types";

/**
 * Wire <-> domain for the case, document and safety-check endpoints (backend ADR 0007).
 *
 * The wire is snake_case and STRICT: a key the backend should not send fails the parse here instead of being
 * silently dropped, exactly like the backend rejects unknown request keys. The domain model keeps the camelCase
 * names the UI already uses. Optional means ABSENT on the wire, never null (ADR 0001).
 */

const Iso = z.string().regex(/^\d{4}-\d{2}-\d{2}/);

export const CaseSummaryWireSchema = z.strictObject({
  id: z.string().min(1),
  code: z.string().min(1),
  age_years: z.number().int().min(0).max(120),
  sex: SexSchema,
  concern: z.string(),
  proposed_treatment: z.string().optional(),
  status: CaseStatusSchema,
  document_count: z.number().int().min(0),
  updated_at: Iso,
  run_id: z.string().min(1).optional(),
  title: z.string().optional(),
});

export const DocumentItemWireSchema = z.strictObject({
  id: z.string().min(1),
  name: z.string().min(1),
  type: DocumentTypeSchema,
  pages: z.number().int().min(1).optional(),
  size_kb: z.number().min(0),
  status: DocumentStatusSchema,
  uploaded_at: Iso,
  ocr_confidence: z.number().min(0).max(1).optional(),
  note: z.string().optional(),
});

export const UploadUrlWireSchema = z.strictObject({
  document_id: z.string().min(1),
  upload_url: z.url(),
  expires_in: z.number().int().min(1),
});

export const SafetyCheckWireSchema = z.strictObject({
  red_flag: z.boolean(),
  matched: z.array(z.string()),
  category: SafetyCheckResultSchema.shape.category,
});

export function decodeCaseSummary(wire: unknown): CaseSummary {
  const w = CaseSummaryWireSchema.parse(wire);
  return CaseSummarySchema.parse({
    id: w.id,
    code: w.code,
    ageYears: w.age_years,
    sex: w.sex,
    concern: w.concern,
    proposedTreatment: w.proposed_treatment,
    status: w.status,
    documentCount: w.document_count,
    updatedAt: w.updated_at,
    runId: w.run_id,
    title: w.title,
  });
}

export function decodeDocumentItem(wire: unknown): DocumentItem {
  const w = DocumentItemWireSchema.parse(wire);
  return DocumentItemSchema.parse({
    id: w.id,
    name: w.name,
    type: w.type,
    pages: w.pages,
    sizeKb: w.size_kb,
    status: w.status,
    uploadedAt: w.uploaded_at,
    ocrConfidence: w.ocr_confidence,
    note: w.note,
  });
}

export function decodeSafetyCheck(wire: unknown): SafetyCheckResult {
  const w = SafetyCheckWireSchema.parse(wire);
  return SafetyCheckResultSchema.parse({ redFlag: w.red_flag, matched: w.matched, category: w.category });
}

/** Optional values the person left empty are omitted, never sent as null or "". */
export function encodeNewCase(input: NewCaseInput): Record<string, unknown> {
  const body: Record<string, unknown> = { concern: input.concern.trim(), age_years: input.ageYears, sex: input.sex };
  if (input.intent?.trim()) body.intent = input.intent.trim();
  if (input.proposedTreatment?.trim()) body.proposed_treatment = input.proposedTreatment.trim();
  return body;
}

export const ALLOWED_UPLOAD_TYPES = ["application/pdf", "image/jpeg", "image/png"] as const;
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

/** A first guess at the document type from the file name; the person can change nothing here yet. */
export function guessDocumentType(name: string): DocumentItem["type"] {
  const n = name.toLowerCase();
  if (/lab|blood|hba1c/.test(n)) return "lab";
  if (/ecg|ekg/.test(n)) return "ecg";
  if (/rx|prescription|medic/.test(n)) return "prescription";
  if (/discharge/.test(n)) return "discharge";
  if (/mri|xray|x-ray|scan|angio|ct/.test(n)) return "imaging";
  if (/consult|opinion|referral/.test(n)) return "consult";
  return "other";
}
