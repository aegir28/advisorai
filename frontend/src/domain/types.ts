import type { z } from "zod";
import type * as S from "./schemas";

/**
 * Domain types for the AdvisorAI frontend.
 *
 * Every type here is INFERRED from its Zod schema in `schemas.ts` (the single
 * source of truth), so the compile-time type and the runtime validator cannot
 * drift apart. Import types from here; import schemas from `./schemas`.
 */

export { SCHEMA_VERSIONS } from "./schemas";

// ── Primitives ───────────────────────────────────────────
export type FactKind = z.infer<typeof S.FactKindSchema>;
export type ContentKind = z.infer<typeof S.ContentKindSchema>;
export type Flag = z.infer<typeof S.FlagSchema>;
export type Confidence = z.infer<typeof S.ConfidenceSchema>;
export type Importance = z.infer<typeof S.ImportanceSchema>;
export type Sex = z.infer<typeof S.SexSchema>;
export type ScenarioId = z.infer<typeof S.ScenarioIdSchema>;
export type CaseStatus = z.infer<typeof S.CaseStatusSchema>;

// ── Case and documents ───────────────────────────────────
export type CaseSummary = z.infer<typeof S.CaseSummarySchema>;
export type DocumentType = z.infer<typeof S.DocumentTypeSchema>;
export type DocumentStatus = z.infer<typeof S.DocumentStatusSchema>;
export type DocumentItem = z.infer<typeof S.DocumentItemSchema>;
export type SourceRef = z.infer<typeof S.SourceRefSchema>;
export type Fact = z.infer<typeof S.FactSchema>;
export type TimelineEvent = z.infer<typeof S.TimelineEventSchema>;
export type TimelineGap = z.infer<typeof S.TimelineGapSchema>;
export type TimelineData = z.infer<typeof S.TimelineDataSchema>;

// ── Specialists (specialist_report.v1) ───────────────────
export type SpecialistId = z.infer<typeof S.SpecialistIdSchema>;
export type Finding = z.infer<typeof S.FindingSchema>;
export type Uncertainty = z.infer<typeof S.UncertaintySchema>;
export type MissingInfo = z.infer<typeof S.MissingInfoSchema>;
export type SpecialistQuestion = z.infer<typeof S.SpecialistQuestionSchema>;
export type EvidenceRef = z.infer<typeof S.EvidenceRefSchema>;
export type SpecialistReport = z.infer<typeof S.SpecialistReportSchema>;
export type RoutingPlan = z.infer<typeof S.RoutingPlanSchema>;
export type PerspectivesData = z.infer<typeof S.PerspectivesDataSchema>;

// ── Cross review ─────────────────────────────────────────
export type CellStance = z.infer<typeof S.CellStanceSchema>;
export type Relationship = z.infer<typeof S.RelationshipSchema>;
export type MatrixRow = z.infer<typeof S.MatrixRowSchema>;
export type CrossReviewData = z.infer<typeof S.CrossReviewDataSchema>;

// ── Evidence and verification ────────────────────────────
export type VerificationStatus = z.infer<typeof S.VerificationStatusSchema>;
export type ExternalSource = z.infer<typeof S.ExternalSourceSchema>;
export type Claim = z.infer<typeof S.ClaimSchema>;
export type EvidenceData = z.infer<typeof S.EvidenceDataSchema>;

// ── Synthesis ────────────────────────────────────────────
export type SynthesisItem = z.infer<typeof S.SynthesisItemSchema>;
export type Synthesis = z.infer<typeof S.SynthesisSchema>;

// ── Report (report.v1) ───────────────────────────────────
export type ReportItem = z.infer<typeof S.ReportItemSchema>;
export type ReportSectionType = z.infer<typeof S.ReportSectionTypeSchema>;
export type ReportSection = z.infer<typeof S.ReportSectionSchema>;
export type PatientReport = z.infer<typeof S.PatientReportSchema>;

// ── Questions ────────────────────────────────────────────
export type QuestionAudience = z.infer<typeof S.QuestionAudienceSchema>;
export type QuestionStatus = z.infer<typeof S.QuestionStatusSchema>;
export type Question = z.infer<typeof S.QuestionSchema>;

// ── Analysis run (run.v1) ────────────────────────────────
export type StepStatus = z.infer<typeof S.StepStatusSchema>;
export type RunStatus = z.infer<typeof S.RunStatusSchema>;
export type RunOutcome = z.infer<typeof S.RunOutcomeSchema>;
export type RunStep = z.infer<typeof S.RunStepSchema>;
export type AnalysisRun = z.infer<typeof S.AnalysisRunSchema>;

// ── Second opinion ───────────────────────────────────────
export type ComparisonRelationship = z.infer<typeof S.ComparisonRelationshipSchema>;
export type ComparisonRow = z.infer<typeof S.ComparisonRowSchema>;
export type SecondOpinionState = z.infer<typeof S.SecondOpinionStateSchema>;
export type Comparison = z.infer<typeof S.ComparisonSchema>;

// ── Trace (trace.v1) ─────────────────────────────────────
export type TraceLevel = z.infer<typeof S.TraceLevelSchema>;
export type TraceNode = z.infer<typeof S.TraceNodeSchema>;
export type Trace = z.infer<typeof S.TraceSchema>;

// ── Canonical case (case.v1) ─────────────────────────────
export type CaseV1 = z.infer<typeof S.CaseV1Schema>;

// ── Aggregates and inputs ────────────────────────────────
export type CaseOverview = z.infer<typeof S.CaseOverviewSchema>;
export type SafetyCheckResult = z.infer<typeof S.SafetyCheckResultSchema>;
export type NewCaseInput = z.infer<typeof S.NewCaseInputSchema>;
