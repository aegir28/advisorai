import { z } from "zod";

/**
 * AdvisorAI contracts: the single source of truth.
 *
 * Every shape the frontend consumes from "the backend" is declared here once,
 * as a Zod schema. The TypeScript types in `types.ts` are INFERRED from these
 * schemas, so a type and its runtime validator can never drift apart. The API
 * layer (`src/lib/api/validate.ts`) parses every response with these schemas,
 * which rejects malformed mock or backend data before it reaches the UI.
 *
 * Versioned contracts carry an explicit `schema_version`:
 *   case.v1 · specialist_report.v1 · report.v1 · trace.v1 · run.v1
 *
 * Naming note: this file is the FRONTEND DOMAIN model. It mixes snake_case
 * (`schema_version`, `run_id`, `missing_info`, ...) and the camelCase names the
 * Phase 1 UI already used (`factRefs`, `routingReason`, ...). The WIRE contract
 * is snake_case throughout (ADR 0001, docs/adr/0001-wire-casing.md): the explicit
 * adapter in `src/lib/api/http/casing.ts` converts at the API boundary, and the
 * backend's Pydantic models in `backend/app/schemas/` mirror the wire form.
 */

export const SCHEMA_VERSIONS = {
  case: "case.v1",
  specialistReport: "specialist_report.v1",
  report: "report.v1",
  trace: "trace.v1",
  run: "run.v1",
} as const;

// ── Primitives ───────────────────────────────────────────
const Id = z.string().min(1);
const IsoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}/, "expected an ISO date");

export const FactKindSchema = z.enum(["patient_fact", "interpretation", "external_evidence"]);
export const ContentKindSchema = z.enum(["patient_fact", "interpretation", "external_evidence", "template"]);
export const FlagSchema = z.enum(["uncertain", "missing", "disagreement"]);
export const ConfidenceSchema = z.enum(["high", "moderate", "low"]);
export const ImportanceSchema = z.enum(["high", "medium", "low"]);
export const SexSchema = z.enum(["F", "M", "X"]);
/** Prototype-only sample identifiers. The real backend has no scenarios. */
export const ScenarioIdSchema = z.enum(["cardiology", "missing_info", "conflicting"]);
export const CaseStatusSchema = z.enum(["draft", "awaiting_upload", "processing", "complete", "partial", "failed"]);

// ── Case and documents ───────────────────────────────────
export const CaseSummarySchema = z.object({
  id: Id,
  /** Pseudonymous display code. Full names never appear on case screens. */
  code: Id,
  /** Prototype-only display string. The real backend never sends a label for the owner. */
  ownerLabel: z.string().optional(),
  ageYears: z.number().int().min(0).max(120),
  sex: SexSchema,
  concern: z.string(),
  proposedTreatment: z.string().optional(),
  status: CaseStatusSchema,
  /** Prototype-only. Absent from real backend responses. */
  scenario: ScenarioIdSchema.optional(),
  documentCount: z.number().int().min(0),
  updatedAt: IsoDate,
  runId: Id.optional(),
  /** Prototype-only. Specialty routing is part of the AI phase, so the real backend does not send it yet. */
  specialtyLabel: z.string().optional(),
  /** Short patient-facing name for lists ("Knee pain"). */
  title: z.string().optional(),
});

export const DocumentTypeSchema = z.enum(["lab", "ecg", "prescription", "discharge", "imaging", "consult", "other"]);
export const DocumentStatusSchema = z.enum(["ready", "processing", "needs_attention", "duplicate"]);

export const DocumentItemSchema = z.object({
  id: Id,
  name: z.string().min(1),
  type: DocumentTypeSchema,
  /** Unknown for a file that could not be read (needs_attention). */
  pages: z.number().int().min(1).optional(),
  sizeKb: z.number().min(0),
  status: DocumentStatusSchema,
  uploadedAt: IsoDate,
  ocrConfidence: z.number().min(0).max(1).optional(),
  note: z.string().optional(),
});

export const SourceRefSchema = z.object({
  docId: Id,
  page: z.number().int().min(1),
  section: z.string().optional(),
  snippet: z.string().min(1),
});

export const FactSchema = z.object({
  id: Id,
  type: z.enum([
    "symptom",
    "lab_result",
    "ecg",
    "procedure_finding",
    "medication",
    "diagnosis",
    "recommendation",
    "treatment_history",
    "imaging",
  ]),
  label: z.string(),
  value: z.string().optional(),
  flag: z.enum(["high", "low", "abnormal"]).optional(),
  date: IsoDate,
  source: SourceRefSchema,
  confidence: z.number().min(0).max(1),
  uncertainValue: z.boolean().optional(),
});

export const TimelineEventSchema = z.object({
  id: Id,
  date: IsoDate,
  precision: z.enum(["day", "month", "approx"]),
  title: z.string(),
  detail: z.string(),
  factId: Id,
  conflict: z.string().optional(),
});

export const TimelineGapSchema = z.object({ id: Id, afterEventId: Id, text: z.string() });

export const TimelineDataSchema = z.object({
  events: z.array(TimelineEventSchema),
  gaps: z.array(TimelineGapSchema),
  checks: z.array(z.string()),
});

// ── Specialists: specialist_report.v1 ────────────────────
export const SpecialistIdSchema = z.enum([
  "general_medicine",
  "cardiology",
  "interventional_cardiology",
  "medication_safety",
  "orthopedics",
  "neurology",
]);

export const FindingSchema = z.object({
  id: Id,
  statement: z.string().min(1),
  kind: FactKindSchema,
  importance: ImportanceSchema,
  factRefs: z.array(Id),
  sourceIds: z.array(Id).optional(),
});

export const UncertaintySchema = z.object({
  id: Id,
  text: z.string().min(1),
  impact: ImportanceSchema,
  resolvableBy: z.string().optional(),
});

export const MissingInfoSchema = z.object({ id: Id, item: z.string().min(1), whyItMatters: z.string() });

export const SpecialistQuestionSchema = z.object({
  id: Id,
  text: z.string().min(1),
  priority: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  /** Finding / uncertainty / missing-info IDs that triggered the question. */
  linkedTo: z.array(Id),
});

export const EvidenceRefSchema = z.object({ sourceId: Id, title: z.string(), section: z.string() });

export const SpecialistReportSchema = z.object({
  schema_version: z.literal(SCHEMA_VERSIONS.specialistReport),
  id: Id,
  run_id: Id,
  case_id: Id,
  /** Specialty identity */
  specialist: SpecialistIdSchema,
  name: z.string().min(1),
  version: z.string().min(1),
  tier: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  priority: z.enum(["mandatory", "optional"]),
  routingReason: z.string(),
  status: z.enum(["complete", "incomplete", "failed"]),
  statusNote: z.string().optional(),
  confidence: z.object({ overall: ConfidenceSchema, reason: z.string() }),
  findings: z.array(FindingSchema),
  uncertainties: z.array(UncertaintySchema),
  missing_info: z.array(MissingInfoSchema),
  contradictions: z.array(z.object({ id: Id, description: z.string(), between: z.array(Id) })),
  considerations: z.array(FindingSchema),
  questions: z.array(SpecialistQuestionSchema),
  evidence_refs: z.array(EvidenceRefSchema),
  limitations: z.array(z.string()),
  /** Specialty-specific additions, e.g. { cardiology: { risk_scores_mentioned: [] } } */
  extensions: z.record(z.string(), z.unknown()).optional(),
});

export const RoutingPlanSchema = z.object({
  selected: z.array(z.object({ specialist: SpecialistIdSchema, priority: z.enum(["mandatory", "optional"]), reason: z.string() })),
  notSelected: z.array(z.object({ name: z.string(), why: z.string() })),
  missingForRouting: z.array(z.string()),
});

export const PerspectivesDataSchema = z.object({
  routing: RoutingPlanSchema,
  reports: z.array(SpecialistReportSchema),
});

// ── Cross review ─────────────────────────────────────────
export const CellStanceSchema = z.enum(["supports", "needs_context", "differs", "flags_issue", "not_assessed"]);
export const RelationshipSchema = z.enum([
  "agreement",
  "partial",
  "disagreement",
  "missing_info",
  "medication_conflict",
  "additional_context",
]);

export const MatrixRowSchema = z.object({
  id: Id,
  topic: z.string(),
  cells: z.partialRecord(SpecialistIdSchema, CellStanceSchema),
  relationship: RelationshipSchema,
  summary: z.string(),
  perspectives: z.array(z.object({ specialist: SpecialistIdSchema, reasoning: z.string() })),
  itemIds: z.array(Id),
});

export const CrossReviewDataSchema = z.object({
  specialists: z.array(z.object({ id: SpecialistIdSchema, name: z.string() })),
  rows: z.array(MatrixRowSchema),
});

// ── Evidence and verification ────────────────────────────
export const VerificationStatusSchema = z.enum([
  "supported",
  "partially_supported",
  "unclear",
  "contradicted",
  "insufficient_evidence",
]);

export const ExternalSourceSchema = z.object({
  id: Id,
  title: z.string(),
  publisher: z.string(),
  year: z.number().int(),
  licence: z.string(),
  section: z.string(),
  snippet: z.string(),
});

export const ClaimSchema = z.object({
  id: Id,
  text: z.string().min(1),
  kind: FactKindSchema,
  agent: SpecialistIdSchema,
  status: VerificationStatusSchema,
  rationale: z.string(),
  patientFactIds: z.array(Id),
  externalSourceIds: z.array(Id),
  /** Removed claims stay visible so people can see what was filtered out. */
  removed: z.boolean().optional(),
  removalReason: z.string().optional(),
});

export const EvidenceDataSchema = z.object({ claims: z.array(ClaimSchema), sources: z.array(ExternalSourceSchema) });

// ── Synthesis ────────────────────────────────────────────
export const SynthesisItemSchema = z.object({
  id: Id,
  text: z.string().min(1),
  kind: FactKindSchema,
  group: z.enum([
    "fact",
    "interpretation",
    "agreement",
    "disagreement",
    "missing",
    "uncertainty",
    "clarification",
    "medication",
    "proposal",
  ]),
  confidence: ConfidenceSchema,
  flag: FlagSchema.optional(),
  derivedFrom: z.array(Id).min(1),
  impact: ImportanceSchema.optional(),
});

export const SynthesisSchema = z.object({
  id: Id,
  /** The reviewer is an AI, never a human doctor. The UI always says so. */
  reviewer: z.object({
    label: z.string(),
    tier: z.union([z.literal(2), z.literal(3)]),
    escalated: z.boolean(),
    escalationReason: z.string().optional(),
  }),
  items: z.array(SynthesisItemSchema),
  rubric: z.array(z.object({ factor: z.string(), weight: z.string() })),
});

// ── Report: report.v1 ────────────────────────────────────
export const ReportSectionTypeSchema = z.enum([
  "prose",
  "bullets",
  "medicines",
  "timeline",
  "perspectives",
  "agreements",
  "disagreements",
  "questions",
  "references",
  "disclaimer",
]);

export const QuestionAudienceSchema = z.enum(["current_doctor", "second_opinion_doctor"]);
export const QuestionStatusSchema = z.enum(["not_asked", "partially_answered", "answered"]);

export const ReportItemSchema = z
  .object({
    /** Stable ID used for traceability. Only fixed template text has none. */
    id: Id.optional(),
    text: z.string().min(1),
    kind: ContentKindSchema,
    flag: FlagSchema.optional(),
    evidenceIds: z.array(Id),
    meta: z.record(z.string(), z.string()).optional(),
  })
  .refine((i) => i.kind === "template" || (!!i.id && i.evidenceIds.length > 0), {
    message: "every non-template report item needs an id and at least one evidence ID",
  });

export const ReportSectionSchema = z.object({
  /** 1..19, fixed. */
  number: z.number().int().min(1).max(19),
  type: ReportSectionTypeSchema,
  items: z.array(ReportItemSchema),
  questionAudience: QuestionAudienceSchema.optional(),
});

export const PatientReportSchema = z
  .object({
    schema_version: z.literal(SCHEMA_VERSIONS.report),
    id: Id,
    caseId: Id,
    runId: Id,
    generatedAt: IsoDate,
    sections: z.array(ReportSectionSchema),
  })
  .refine((r) => r.sections.length === 19 && r.sections.every((s, i) => s.number === i + 1), {
    message: "a report has exactly the 19 blueprint sections, numbered 1..19 in order",
    path: ["sections"],
  });

// ── Questions ────────────────────────────────────────────
export const QuestionSchema = z.object({
  id: Id,
  audience: QuestionAudienceSchema,
  priority: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  category: z.string(),
  text: z.string().min(1),
  /** Why this question was generated for this person. */
  trigger: z.string(),
  linkedItemIds: z.array(Id).min(1),
  status: QuestionStatusSchema,
  note: z.string().optional(),
});

// ── Analysis run: run.v1 ─────────────────────────────────
export const StepStatusSchema = z.enum(["pending", "running", "done", "warning", "failed", "skipped"]);
export const RunStatusSchema = z.enum(["running", "complete", "partial", "failed"]);
export const RunOutcomeSchema = z.enum(["complete", "partial", "failed"]);

export const RunStepSchema = z.object({
  /** 1..14, title from i18n key run.s{n} */
  n: z.number().int().min(1).max(14),
  status: StepStatusSchema,
  note: z.string().optional(),
});

export const AnalysisRunSchema = z
  .object({
    schema_version: z.literal(SCHEMA_VERSIONS.run),
    id: Id,
    caseId: Id,
    status: RunStatusSchema,
    progress: z.number().min(0).max(1),
    steps: z.array(RunStepSchema),
    startedAt: IsoDate,
    finishedAt: IsoDate.optional(),
    /** Present when a critical failure stops the run. */
    failure: z.object({ title: z.string(), body: z.string() }).optional(),
    /** Present when the run finished with gaps. */
    warnings: z.array(z.string()),
  })
  .refine((r) => r.steps.length === 14 && r.steps.every((s, i) => s.n === i + 1), {
    message: "a run has exactly the 14 workflow steps, numbered 1..14 in order",
    path: ["steps"],
  })
  .refine((r) => r.status !== "failed" || !!r.failure, {
    message: "a failed run must explain itself in `failure`",
    path: ["failure"],
  });

// ── Second opinion ───────────────────────────────────────
export const ComparisonRelationshipSchema = z.enum(["agreement", "differs", "new_info", "changed", "unresolved"]);

export const ComparisonRowSchema = z.object({
  id: Id,
  topic: z.string(),
  opinionA: z.string(),
  opinionB: z.string(),
  evidenceA: z.array(Id),
  evidenceB: z.array(Id),
  relationship: ComparisonRelationshipSchema,
  itemIds: z.array(Id),
});

export const SecondOpinionStateSchema = z.object({
  status: z.enum(["none", "processing", "ready"]),
  documentName: z.string().optional(),
});

export const ComparisonSchema = z.object({
  opinionALabel: z.string(),
  opinionBLabel: z.string(),
  rows: z.array(ComparisonRowSchema),
  nextQuestions: z.array(z.object({ audience: z.string(), text: z.string(), itemIds: z.array(Id) })),
  /** Question IDs the second opinion appears to address. */
  answeredByOpinion: z.array(z.object({ questionId: Id, note: z.string(), status: QuestionStatusSchema })),
});

// ── Trace: trace.v1 ──────────────────────────────────────
export const TraceLevelSchema = z.enum([
  "report",
  "synthesis",
  "specialist",
  "verification",
  "evidence_source",
  "fact",
  "timeline",
  "matrix",
  "question",
  "comparison",
]);

export const TraceNodeSchema = z.object({
  id: Id,
  level: TraceLevelSchema,
  text: z.string(),
  kind: ContentKindSchema.optional(),
  flag: FlagSchema.optional(),
  status: VerificationStatusSchema.optional(),
  /** Free-form label, e.g. "Cardiology perspective". */
  label: z.string().optional(),
  source: SourceRefSchema.optional(),
  externalSource: ExternalSourceSchema.optional(),
  get children() {
    return z.array(TraceNodeSchema);
  },
});

export const TraceSchema = z.object({
  schema_version: z.literal(SCHEMA_VERSIONS.trace),
  itemId: Id,
  root: TraceNodeSchema,
});

// ── Canonical case: case.v1 ──────────────────────────────
const FactItem = z.object({ text: z.string(), fact_ref: Id });
const TestItem = z.object({ name: z.string(), value: z.string().optional(), flag: z.string().optional(), date: IsoDate, fact_ref: Id });

/**
 * The canonical structured case the backend stores and hands to agents
 * (blueprint: "Structured patient case"). Identity fields (names, phone, email,
 * hospital IDs) are never part of it: agents see pseudonymous slices only.
 */
export const CaseV1Schema = z.object({
  schema_version: z.literal(SCHEMA_VERSIONS.case),
  case_id: Id,
  demographics: z.object({ age: z.number().int().min(0).max(120), sex: SexSchema }),
  chief_concern: z.string(),
  symptoms: z.array(z.object({ text: z.string(), onset: z.string().optional(), fact_ref: Id })),
  diagnoses: z.array(z.object({ name: z.string(), status: z.enum(["documented", "suspected"]), fact_ref: Id })),
  history: z.array(FactItem),
  allergies: z.array(FactItem),
  medications: z.array(z.object({ name: z.string(), dose: z.string().optional(), freq: z.string().optional(), start: z.string().optional(), fact_ref: Id })),
  investigations: z.object({
    labs: z.array(TestItem),
    imaging: z.array(TestItem),
    ecg: z.array(TestItem),
    pathology: z.array(TestItem),
  }),
  procedures: z.array(FactItem),
  surgeries: z.array(FactItem),
  treatment_history: z.array(FactItem),
  recommendations: z.array(z.object({ by: z.string(), text: z.string(), fact_ref: Id })),
  proposed: z.object({ treatment: z.array(z.string()), procedure: z.array(z.string()) }),
  timeline_ref: Id,
  unresolved_questions: z.array(z.string()),
  missing_information: z.array(z.object({ item: z.string(), why_matters: z.string() })),
  evidence_refs: z.array(Id),
  extensions: z.record(z.string(), z.unknown()),
});

// ── Aggregates returned per case ─────────────────────────
export const CaseOverviewSchema = z.object({
  summary: CaseSummarySchema,
  documents: z.array(DocumentItemSchema),
  /** Quick highlights shown on the overview; each links to a trace. */
  highlights: z.array(z.object({ id: Id, text: z.string(), flag: FlagSchema.optional() })),
  analysisAvailable: z.boolean(),
});

export const SafetyCheckResultSchema = z.object({
  redFlag: z.boolean(),
  matched: z.array(z.string()),
  category: z.enum(["cardiac", "stroke", "breathing", "bleeding", "self_harm"]).optional(),
});

export const NewCaseInputSchema = z.object({
  /** What the person wants help with ("Understanding my treatment"). */
  intent: z.string().optional(),
  concern: z.string().min(1),
  proposedTreatment: z.string().optional(),
  ageYears: z.number().int().min(0).max(120),
  sex: SexSchema,
  /** Prototype-only. */
  scenario: ScenarioIdSchema.optional(),
});

export const StartAnalysisResultSchema = z.object({ runId: Id });

// ── API error envelope (backend ADR 0002) ────────────────
/**
 * Every /api/v1 error response. This is a WIRE shape (snake_case), validated before it is turned
 * into an `ApiError`. `code` is a plain string so a code added by a newer backend still parses.
 */
export const ErrorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string().min(1),
    message: z.string(),
    request_id: z.string().min(1),
    details: z.record(z.string(), z.unknown()).default({}),
  }),
});
