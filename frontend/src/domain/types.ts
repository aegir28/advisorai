/**
 * Domain model for the AdvisorAI frontend.
 *
 * These types mirror the shapes described in the architecture blueprint
 * (case.v1, specialist_report.v1, claim verification, trace chain, report
 * sections, questions, comparison). The future backend must return the same
 * shapes so the UI does not need to change.
 */

export type FactKind = "patient_fact" | "interpretation" | "external_evidence";
export type ContentKind = FactKind | "template";
export type Flag = "uncertain" | "missing" | "disagreement";
export type Confidence = "high" | "moderate" | "low";
export type Importance = "high" | "medium" | "low";
export type Sex = "F" | "M" | "X";

export type ScenarioId = "cardiology" | "missing_info" | "conflicting";

export type CaseStatus = "draft" | "awaiting_upload" | "processing" | "complete" | "partial" | "failed";

// ── Case & documents ───────────────────────────────────
export interface CaseSummary {
  id: string;
  /** Pseudonymous display code. Full names never appear on case screens. */
  code: string;
  ownerLabel: string;
  ageYears: number;
  sex: Sex;
  concern: string;
  proposedTreatment?: string;
  status: CaseStatus;
  scenario: ScenarioId;
  documentCount: number;
  updatedAt: string;
  runId?: string;
  specialtyLabel: string;
  /** Short patient-facing name for lists ("Knee pain"). Optional and additive. */
  title?: string;
}

export type DocumentType = "lab" | "ecg" | "prescription" | "discharge" | "imaging" | "consult" | "other";
export type DocumentStatus = "ready" | "processing" | "needs_attention" | "duplicate";

export interface DocumentItem {
  id: string;
  name: string;
  type: DocumentType;
  pages: number;
  sizeKb: number;
  status: DocumentStatus;
  uploadedAt: string;
  ocrConfidence?: number;
  note?: string;
}

export interface SourceRef {
  docId: string;
  page: number;
  section?: string;
  snippet: string;
}

export interface Fact {
  id: string;
  type:
    | "symptom"
    | "lab_result"
    | "ecg"
    | "procedure_finding"
    | "medication"
    | "diagnosis"
    | "recommendation"
    | "treatment_history"
    | "imaging";
  label: string;
  value?: string;
  flag?: "high" | "low" | "abnormal";
  date: string;
  source: SourceRef;
  confidence: number;
  uncertainValue?: boolean;
}

export interface TimelineEvent {
  id: string;
  date: string;
  precision: "day" | "month" | "approx";
  title: string;
  detail: string;
  factId: string;
  conflict?: string;
}

export interface TimelineGap {
  id: string;
  afterEventId: string;
  text: string;
}

// ── Specialists ───────────────────────────────────
export type SpecialistId =
  | "general_medicine"
  | "cardiology"
  | "interventional_cardiology"
  | "medication_safety"
  | "orthopedics"
  | "neurology";

export interface Finding {
  id: string;
  statement: string;
  kind: FactKind;
  importance: Importance;
  factRefs: string[];
  sourceIds?: string[];
}

export interface Uncertainty {
  id: string;
  text: string;
  impact: Importance;
  resolvableBy?: string;
}

export interface MissingInfo {
  id: string;
  item: string;
  whyItMatters: string;
}

export interface SpecialistReport {
  id: string;
  specialist: SpecialistId;
  name: string;
  version: string;
  tier: 1 | 2 | 3;
  priority: "mandatory" | "optional";
  routingReason: string;
  status: "complete" | "incomplete" | "failed";
  statusNote?: string;
  confidence: { overall: Confidence; reason: string };
  findings: Finding[];
  uncertainties: Uncertainty[];
  missing: MissingInfo[];
  contradictions: { id: string; description: string; between: string[] }[];
  considerations: Finding[];
  limitations: string[];
}

export interface RoutingPlan {
  selected: { specialist: SpecialistId; priority: "mandatory" | "optional"; reason: string }[];
  notSelected: { name: string; why: string }[];
  missingForRouting: string[];
}

// ── Cross review ─────────────────────────────────
export type CellStance = "supports" | "needs_context" | "differs" | "flags_issue" | "not_assessed";
export type Relationship =
  | "agreement"
  | "partial"
  | "disagreement"
  | "missing_info"
  | "medication_conflict"
  | "additional_context";

export interface MatrixRow {
  id: string;
  topic: string;
  cells: Partial<Record<SpecialistId, CellStance>>;
  relationship: Relationship;
  summary: string;
  perspectives: { specialist: SpecialistId; reasoning: string }[];
  itemIds: string[];
}

// ── Evidence & verification ──────────────────────
export type VerificationStatus =
  | "supported"
  | "partially_supported"
  | "unclear"
  | "contradicted"
  | "insufficient_evidence";

export interface ExternalSource {
  id: string;
  title: string;
  publisher: string;
  year: number;
  licence: string;
  section: string;
  snippet: string;
}

export interface Claim {
  id: string;
  text: string;
  kind: FactKind;
  agent: SpecialistId;
  status: VerificationStatus;
  rationale: string;
  patientFactIds: string[];
  externalSourceIds: string[];
  /** Removed claims stay visible so people can see what was filtered out. */
  removed?: boolean;
  removalReason?: string;
}

// ── Synthesis ────────────────────────────────────
export interface SynthesisItem {
  id: string;
  text: string;
  kind: FactKind;
  group:
    | "fact"
    | "interpretation"
    | "agreement"
    | "disagreement"
    | "missing"
    | "uncertainty"
    | "clarification"
    | "medication"
    | "proposal";
  confidence: Confidence;
  flag?: Flag;
  derivedFrom: string[];
  impact?: Importance;
}

export interface Synthesis {
  id: string;
  /** The reviewer is an AI, never a human doctor. The UI always says so. */
  reviewer: { label: string; tier: 2 | 3; escalated: boolean; escalationReason?: string };
  items: SynthesisItem[];
  rubric: { factor: string; weight: string }[];
}

// ── Report ───────────────────────────────────────
export interface ReportItem {
  /** Stable ID used for traceability. Template items have none. */
  id?: string;
  text: string;
  kind: ContentKind;
  flag?: Flag;
  evidenceIds: string[];
  meta?: Record<string, string>;
}

export type ReportSectionType =
  | "prose"
  | "bullets"
  | "medicines"
  | "timeline"
  | "perspectives"
  | "agreements"
  | "disagreements"
  | "questions"
  | "references"
  | "disclaimer";

export interface ReportSection {
  /** 1..19, fixed. Title comes from i18n key report.s{number}. */
  number: number;
  type: ReportSectionType;
  items: ReportItem[];
  questionAudience?: QuestionAudience;
}

export interface PatientReport {
  id: string;
  caseId: string;
  runId: string;
  generatedAt: string;
  sections: ReportSection[];
}

// ── Questions ────────────────────────────────────
export type QuestionAudience = "current_doctor" | "second_opinion_doctor";
export type QuestionStatus = "not_asked" | "partially_answered" | "answered";

export interface Question {
  id: string;
  audience: QuestionAudience;
  priority: 1 | 2 | 3;
  category: string;
  text: string;
  /** Why this question was generated for this person. */
  trigger: string;
  linkedItemIds: string[];
  status: QuestionStatus;
  note?: string;
}

// ── Analysis run ─────────────────────────────────
export type StepStatus = "pending" | "running" | "done" | "warning" | "failed" | "skipped";
export type RunStatus = "running" | "complete" | "partial" | "failed";
export type RunOutcome = "complete" | "partial" | "failed";

export interface RunStep {
  /** 1..14, title from i18n key run.s{n} */
  n: number;
  status: StepStatus;
  note?: string;
}

export interface AnalysisRun {
  id: string;
  caseId: string;
  status: RunStatus;
  progress: number;
  steps: RunStep[];
  startedAt: string;
  finishedAt?: string;
  /** Shown when a critical failure stops the run. */
  failure?: { title: string; body: string };
  /** Shown when the run finished, but with gaps. */
  warnings: string[];
}

// ── Second opinion ───────────────────────────────
export type ComparisonRelationship = "agreement" | "differs" | "new_info" | "changed" | "unresolved";

export interface ComparisonRow {
  id: string;
  topic: string;
  opinionA: string;
  opinionB: string;
  evidenceA: string[];
  evidenceB: string[];
  relationship: ComparisonRelationship;
  itemIds: string[];
}

export interface SecondOpinionState {
  status: "none" | "processing" | "ready";
  documentName?: string;
}

export interface Comparison {
  opinionALabel: string;
  opinionBLabel: string;
  rows: ComparisonRow[];
  nextQuestions: { audience: string; text: string; itemIds: string[] }[];
  /** Question IDs the second opinion appears to address. */
  answeredByOpinion: { questionId: string; note: string; status: QuestionStatus }[];
}

// ── Trace ────────────────────────────────────────
export type TraceLevel =
  | "report"
  | "synthesis"
  | "specialist"
  | "verification"
  | "evidence_source"
  | "fact"
  | "timeline"
  | "matrix"
  | "question"
  | "comparison";

export interface TraceNode {
  id: string;
  level: TraceLevel;
  text: string;
  kind?: ContentKind;
  flag?: Flag;
  status?: VerificationStatus;
  /** Free-form label, e.g. "Cardiology perspective". */
  label?: string;
  source?: SourceRef;
  externalSource?: ExternalSource;
  children: TraceNode[];
}

export interface Trace {
  itemId: string;
  root: TraceNode;
}

// ── Aggregates returned per case ─────────────────
export interface TimelineData {
  events: TimelineEvent[];
  gaps: TimelineGap[];
  checks: string[];
}

export interface PerspectivesData {
  routing: RoutingPlan;
  reports: SpecialistReport[];
}

export interface EvidenceData {
  claims: Claim[];
  sources: ExternalSource[];
}

export interface CrossReviewData {
  specialists: { id: SpecialistId; name: string }[];
  rows: MatrixRow[];
}

export interface CaseOverview {
  summary: CaseSummary;
  documents: DocumentItem[];
  /** Quick highlights shown on the overview; each links to a trace. */
  highlights: { id: string; text: string; flag?: Flag }[];
  analysisAvailable: boolean;
}

export interface SafetyCheckResult {
  redFlag: boolean;
  matched: string[];
  category?: "cardiac" | "stroke" | "breathing" | "bleeding" | "self_harm";
}

export interface NewCaseInput {
  /** What the person wants help with ("Understanding my treatment"). Optional and additive. */
  intent?: string;
  concern: string;
  proposedTreatment?: string;
  ageYears: number;
  sex: Sex;
  scenario?: ScenarioId;
}
