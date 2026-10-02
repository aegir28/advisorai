import type { CaseSummary, RunOutcome, ScenarioId, Sex } from "@/domain/types";

/** A fictional sample case a person can pick in the prototype. */
export interface SampleCase {
  id: ScenarioId;
  title: string;
  blurb: string;
  ageYears: number;
  sex: Sex;
  documentCount: number;
}

/**
 * Controls that only make sense while the app runs on mock data. They are
 * deliberately NOT part of `AdvisorApi`, so a real backend never has to
 * implement them and production code cannot depend on them.
 */
export interface PrototypeControls {
  /** Fictional sample cases to choose from instead of uploading real files. */
  listSampleCases(): SampleCase[];
  /** Replace a case's documents with a sample case's synthetic documents. */
  attachSampleRecords(caseId: string, scenario: ScenarioId): Promise<CaseSummary>;
  /** Decide how the NEXT analysis of this case should end (partial and failed demos). */
  setNextRunOutcome(caseId: string, outcome?: RunOutcome): void;
  /** Skip the simulated waiting time. */
  skipToResults(runId: string): Promise<void>;
}
