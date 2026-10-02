import type {
  AnalysisRun,
  CaseOverview,
  CaseSummary,
  Comparison,
  CrossReviewData,
  DocumentItem,
  EvidenceData,
  NewCaseInput,
  PatientReport,
  PerspectivesData,
  Question,
  QuestionStatus,
  SafetyCheckResult,
  SecondOpinionState,
  Synthesis,
  TimelineData,
  Trace,
} from "@/domain/types";

export interface SafetyCheckInput {
  text: string;
  /** Symptoms the person ticked as happening right now. */
  currentSymptoms: string[];
}

/**
 * The only surface the UI uses to talk to "the backend". This is the PRODUCTION
 * contract: it contains nothing that is specific to the mock. Demo-only controls
 * live in `src/lib/prototype.ts`.
 *
 * Every response is validated against the Zod schemas in `src/domain/schemas.ts`
 * by `src/lib/api/validate.ts` before it reaches the UI.
 *
 * The mock implementation lives in src/mocks. The FastAPI client will
 * implement this exact interface (see docs/frontend-data-contract.md).
 *
 * Endpoint mapping (blueprint API structure, /api/v1):
 *   listCases/getCase/createCase  → GET/POST /cases, GET /cases/{id}
 *   safetyCheck                   → POST /cases/{id}/safety-check
 *   getDocuments/uploadDocument   → GET /cases/{id}/documents, upload-url + complete
 *   startAnalysis/getRun          → POST /cases/{id}/analysis, GET /analysis/{run_id}
 *   getTimeline                   → GET /cases/{id}/timeline
 *   getPerspectives/…             → GET /runs/{run_id}/perspectives
 *   getReport                     → GET /runs/{run_id}/report
 *   getQuestions                  → GET /runs/{run_id}/questions
 *   getTrace                      → GET /runs/{run_id}/trace/{item_id}
 *   submitSecondOpinion/…         → POST /cases/{id}/second-opinions, GET /cases/{id}/comparison
 */
export interface AdvisorApi {
  listCases(): Promise<CaseSummary[]>;
  getCase(caseId: string): Promise<CaseSummary | null>;
  getCaseOverview(caseId: string): Promise<CaseOverview | null>;
  createCase(input: NewCaseInput): Promise<CaseSummary>;
  deleteCase(caseId: string): Promise<void>;
  safetyCheck(input: SafetyCheckInput): Promise<SafetyCheckResult>;

  getDocuments(caseId: string): Promise<DocumentItem[]>;
  /**
   * `blob` is the real file. The mock ignores it; the HTTP implementation requires it (it uploads straight to
   * private storage through a short-lived signed URL, then asks the backend to validate it).
   */
  uploadDocument(caseId: string, file: { name: string; sizeKb: number; blob?: Blob }): Promise<DocumentItem>;
  removeDocument(caseId: string, docId: string): Promise<void>;

  startAnalysis(caseId: string): Promise<{ runId: string }>;
  getRun(runId: string): Promise<AnalysisRun | null>;

  getTimeline(caseId: string): Promise<TimelineData | null>;
  getPerspectives(caseId: string): Promise<PerspectivesData | null>;
  getEvidence(caseId: string): Promise<EvidenceData | null>;
  getCrossReview(caseId: string): Promise<CrossReviewData | null>;
  getSynthesis(caseId: string): Promise<Synthesis | null>;
  getReport(caseId: string): Promise<PatientReport | null>;
  getQuestions(caseId: string): Promise<Question[] | null>;
  updateQuestion(caseId: string, questionId: string, patch: { status?: QuestionStatus; note?: string }): Promise<Question>;
  getTrace(caseId: string, itemId: string): Promise<Trace | null>;

  getSecondOpinion(caseId: string): Promise<SecondOpinionState>;
  submitSecondOpinion(caseId: string, file: { name: string }): Promise<SecondOpinionState>;
  getComparison(caseId: string): Promise<Comparison | null>;
}
