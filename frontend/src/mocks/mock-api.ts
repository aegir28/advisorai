import type {
  AnalysisRun,
  CaseSummary,
  DocumentItem,
  NewCaseInput,
  Question,
  RunOutcome,
  RunStep,
  SafetyCheckResult,
  ScenarioId,
  SecondOpinionState,
} from "@/domain/types";
import { SCHEMA_VERSIONS } from "@/domain/schemas";
import type { AdvisorApi, SafetyCheckInput } from "@/lib/api/types";
import type { PrototypeControls, SampleCase } from "@/lib/prototype-types";
import { buildCrossReview, buildEvidence, buildPerspectives, buildReport, buildTrace } from "./builders";
import { scenarioBlurbs, scenarioList, scenarios, seededCaseIds } from "./scenarios";
import type { ScenarioData } from "./scenarios/types";

/**
 * In-memory, localStorage-backed mock of the AdvisorAI backend.
 * Everything here is synthetic. Nothing leaves the browser.
 */

const STORAGE_KEY = "advisorai.mock.v1";
const STEP_MS = 1300;
const TOTAL_STEPS = 14;

interface RunRecord {
  id: string;
  caseId: string;
  startedAt: number;
  outcome: RunOutcome;
  /** Set when the user chooses "skip to results". */
  skipped?: boolean;
}

interface Store {
  createdCases: CaseSummary[];
  caseOverrides: Record<string, Partial<CaseSummary>>;
  documents: Record<string, DocumentItem[]>;
  runs: Record<string, RunRecord>;
  questionState: Record<string, Record<string, { status: Question["status"]; note?: string }>>;
  secondOpinion: Record<string, { startedAt: number; documentName: string }>;
  deleted: string[];
  /** Prototype only: how the next analysis of a case should end. */
  pendingOutcome: Record<string, RunOutcome | undefined>;
}

const emptyStore = (): Store => ({
  createdCases: [], caseOverrides: {}, documents: {}, runs: {}, questionState: {}, secondOpinion: {}, deleted: [], pendingOutcome: {},
});

let memory: Store | null = null;

function store(): Store {
  if (memory) return memory;
  let loaded: Store | null = null;
  try {
    if (typeof window !== "undefined") {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) loaded = { ...emptyStore(), ...(JSON.parse(raw) as Partial<Store>) };
    }
  } catch {
    loaded = null;
  }
  memory = loaded ?? emptyStore();
  return memory;
}

function save() {
  try {
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store()));
  } catch {
    /* storage may be unavailable (private mode); the prototype still works in memory */
  }
}

const delay = (ms = 220) => new Promise<void>((resolve) => setTimeout(resolve, ms));

// ── Lookup helpers ───────────────────────────────────────

function seedCases(): CaseSummary[] {
  return (Object.values(seededCaseIds) as ScenarioId[]).map((id) => scenarios[id].seedCase);
}

function allCases(): CaseSummary[] {
  const s = store();
  return [...s.createdCases, ...seedCases()]
    .filter((c) => !s.deleted.includes(c.id))
    .map((c) => ({ ...c, ...(s.caseOverrides[c.id] ?? {}) }))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

function findCase(caseId: string): CaseSummary | null {
  return allCases().find((c) => c.id === caseId) ?? null;
}

function scenarioFor(c: CaseSummary): ScenarioData {
  return scenarios[c.scenario ?? "cardiology"];
}

function patchCase(caseId: string, patch: Partial<CaseSummary>) {
  const s = store();
  const created = s.createdCases.find((c) => c.id === caseId);
  if (created) Object.assign(created, patch);
  else s.caseOverrides[caseId] = { ...(s.caseOverrides[caseId] ?? {}), ...patch };
  save();
}

function hasResults(c: CaseSummary): boolean {
  return c.status === "complete" || c.status === "partial";
}

// ── Runs ─────────────────────────────────────────────────

function seededRun(c: CaseSummary): AnalysisRun {
  const sc = scenarioFor(c);
  const steps: RunStep[] = Array.from({ length: TOTAL_STEPS }, (_, i) => ({
    n: i + 1,
    status: sc.stepNotes[i + 1] ? "warning" : "done",
    note: sc.stepNotes[i + 1],
  }));
  return {
    schema_version: SCHEMA_VERSIONS.run,
    id: c.runId ?? "r_seed", caseId: c.id, status: sc.finalStatus, progress: 1, steps,
    startedAt: new Date(Date.parse(c.updatedAt) - 4 * 60_000).toISOString(), finishedAt: c.updatedAt, warnings: sc.runWarnings,
  };
}

function computeRun(rec: RunRecord): AnalysisRun {
  const c = findCase(rec.caseId);
  const sc = c ? scenarioFor(c) : scenarios.cardiology;
  const elapsed = rec.skipped ? Number.MAX_SAFE_INTEGER : Date.now() - rec.startedAt;
  const current = Math.floor(elapsed / STEP_MS); // index of the step now running (0-based)
  const failAt = 4;
  const partialNotes: Record<number, string> = Object.keys(sc.stepNotes).length
    ? (sc.stepNotes as Record<number, string>)
    : { 2: "One file couldn't be read clearly.", 7: "One perspective didn't finish; continuing without it." };

  const steps: RunStep[] = Array.from({ length: TOTAL_STEPS }, (_, i): RunStep => {
    const n = i + 1;
    if (rec.outcome === "failed" && n === failAt && current >= i) {
      return { n, status: "failed", note: "A document was too blurry to read safely." };
    }
    if (rec.outcome === "failed" && current >= failAt - 1 && n > failAt) {
      return { n, status: "skipped", note: "Not started, because an earlier step couldn't finish." };
    }
    if (i < current) {
      if (rec.outcome === "partial" && partialNotes[n]) return { n, status: "warning", note: partialNotes[n] };
      return { n, status: "done" };
    }
    if (i === current) return { n, status: "running" };
    return { n, status: "pending" };
  });

  const failed = rec.outcome === "failed" && current >= failAt - 1;
  const finished = failed || current >= TOTAL_STEPS;
  const status: AnalysisRun["status"] = !finished ? "running" : failed ? "failed" : rec.outcome === "partial" ? "partial" : "complete";
  const progress = failed ? (failAt - 1) / TOTAL_STEPS : Math.min(1, current / TOTAL_STEPS);

  return {
    schema_version: SCHEMA_VERSIONS.run,
    id: rec.id, caseId: rec.caseId, status, progress, steps,
    startedAt: new Date(rec.startedAt).toISOString(),
    finishedAt: finished ? new Date().toISOString() : undefined,
    failure: failed
      ? { title: "We couldn't finish reading your records", body: "One document looked too blurry to read safely, so we stopped rather than guess. Please add a clearer copy and try again. Nothing was shared or lost." }
      : undefined,
    warnings: finished && rec.outcome === "partial" ? (sc.runWarnings.length ? sc.runWarnings : ["Some documents or perspectives could not be completed. The report says so wherever it matters."]) : [],
  };
}

/** When a run finishes, move the case to its final state exactly once. */
function settle(run: AnalysisRun) {
  if (run.status === "running") return;
  const c = findCase(run.caseId);
  // Only the case's current run may settle it (a stale run must not overwrite a retry).
  if (!c || c.status !== "processing" || c.runId !== run.id) return;
  patchCase(c.id, { status: run.status, updatedAt: new Date().toISOString() });
}

// ── Safety gate ──────────────────────────────────────────

const RED_FLAGS: { re: RegExp; category: NonNullable<SafetyCheckResult["category"]> }[] = [
  { re: /chest pain (right )?now|pain in (my )?chest (right )?now|crushing chest/i, category: "cardiac" },
  { re: /stroke|face (is )?drooping|slurred speech|sudden weakness/i, category: "stroke" },
  { re: /can'?t breathe|cannot breathe|breathless at rest|short of breath at rest|struggling to breathe/i, category: "breathing" },
  { re: /heavy bleeding|bleeding (heavily|a lot)|won'?t stop bleeding/i, category: "bleeding" },
  { re: /suicid|kill myself|end my life|want to die|harm myself/i, category: "self_harm" },
];

const SYMPTOM_CATEGORY: Record<string, NonNullable<SafetyCheckResult["category"]>> = {
  chest_pain_now: "cardiac", stroke_signs: "stroke", breathless_rest: "breathing", heavy_bleeding: "bleeding", self_harm: "self_harm",
};

function runSafetyCheck(input: SafetyCheckInput): SafetyCheckResult {
  const matched: string[] = [];
  let category: SafetyCheckResult["category"];
  for (const sym of input.currentSymptoms) {
    matched.push(sym);
    category ??= SYMPTOM_CATEGORY[sym];
  }
  for (const rule of RED_FLAGS) {
    const hit = input.text.match(rule.re);
    if (hit) {
      matched.push(hit[0]);
      category ??= rule.category;
    }
  }
  return { redFlag: matched.length > 0, matched, category };
}

// ── API ─────────────────────────────────────────────────

function requireResults(caseId: string): { c: CaseSummary; sc: ScenarioData } | null {
  const c = findCase(caseId);
  if (!c || !hasResults(c)) return null;
  return { c, sc: scenarioFor(c) };
}

function mergedQuestions(c: CaseSummary, sc: ScenarioData): Question[] {
  const overrides = store().questionState[c.id] ?? {};
  return sc.questions.map((q) => ({ ...q, ...(overrides[q.id] ?? {}) }));
}

function secondOpinionState(c: CaseSummary): SecondOpinionState {
  const so = store().secondOpinion[c.id];
  if (!so) return { status: "none" };
  const ready = Date.now() - so.startedAt > 3200;
  return { status: ready ? "ready" : "processing", documentName: so.documentName };
}

export const mockApi: AdvisorApi = {
  async listCases() {
    await delay();
    return allCases();
  },

  async getCase(caseId) {
    await delay(120);
    return findCase(caseId);
  },

  async getCaseOverview(caseId) {
    await delay(160);
    const c = findCase(caseId);
    if (!c) return null;
    const sc = scenarioFor(c);
    const documents = store().documents[caseId] ?? (seededCaseIds[caseId] ? sc.documents : []);
    return { summary: c, documents, highlights: hasResults(c) ? sc.highlights : [], analysisAvailable: hasResults(c) };
  },

  async createCase(input: NewCaseInput) {
    await delay(300);
    const id = `c_${Math.random().toString(16).slice(2, 5)}`;
    const code = `AC-${id.slice(2).toUpperCase()}`;
    const c: CaseSummary = {
      id, code, ownerLabel: "You (synthetic demo)", title: input.intent ?? "New case", ageYears: input.ageYears, sex: input.sex, concern: input.concern,
      proposedTreatment: input.proposedTreatment || undefined, status: "awaiting_upload", scenario: input.scenario ?? "cardiology",
      documentCount: 0, updatedAt: new Date().toISOString(), specialtyLabel: "New case",
    };
    store().createdCases.unshift(c);
    store().documents[id] = [];
    save();
    return c;
  },

  async deleteCase(caseId) {
    await delay();
    const s = store();
    s.createdCases = s.createdCases.filter((c) => c.id !== caseId);
    if (!s.deleted.includes(caseId)) s.deleted.push(caseId);
    delete s.documents[caseId];
    save();
  },

  async safetyCheck(input) {
    await delay(350);
    return runSafetyCheck(input);
  },

  async getDocuments(caseId) {
    await delay(150);
    const c = findCase(caseId);
    if (!c) return [];
    return store().documents[caseId] ?? (seededCaseIds[caseId] ? scenarioFor(c).documents : []);
  },

  async uploadDocument(caseId, file) {
    await delay(700);
    const lower = file.name.toLowerCase();
    const doc: DocumentItem = {
      id: `d_up_${Math.random().toString(16).slice(2, 7)}`, name: file.name,
      type: /lab|blood|hba1c/.test(lower) ? "lab" : /ecg/.test(lower) ? "ecg" : /rx|prescription|medic/.test(lower) ? "prescription" : /mri|xray|x-ray|scan|angio/.test(lower) ? "imaging" : "other",
      pages: 1, sizeKb: file.sizeKb, status: "ready", uploadedAt: new Date().toISOString(),
      note: "Prototype: files are not read. Results come from the sample case you choose.",
    };
    const s = store();
    s.documents[caseId] = [...(s.documents[caseId] ?? []), doc];
    patchCase(caseId, { documentCount: s.documents[caseId].length });
    return doc;
  },

  async removeDocument(caseId, docId) {
    await delay(200);
    const s = store();
    s.documents[caseId] = (s.documents[caseId] ?? []).filter((d) => d.id !== docId);
    patchCase(caseId, { documentCount: s.documents[caseId].length });
  },

  async startAnalysis(caseId) {
    await delay(300);
    const c = findCase(caseId);
    if (!c) throw new Error("Case not found");
    const sc = scenarioFor(c);
    const runId = `r_${Math.random().toString(16).slice(2, 6)}`;
    store().runs[runId] = { id: runId, caseId, startedAt: Date.now(), outcome: store().pendingOutcome[caseId] ?? sc.finalStatus };
    delete store().pendingOutcome[caseId];
    patchCase(caseId, { status: "processing", runId, updatedAt: new Date().toISOString() });
    return { runId };
  },

  async getRun(runId) {
    await delay(120);
    const rec = store().runs[runId];
    if (rec) {
      const run = computeRun(rec);
      settle(run);
      return run;
    }
    const seeded = allCases().find((c) => c.runId === runId);
    return seeded ? seededRun(seeded) : null;
  },

  async getTimeline(caseId) {
    await delay();
    const r = requireResults(caseId);
    return r ? r.sc.timeline : null;
  },

  async getPerspectives(caseId) {
    await delay();
    const r = requireResults(caseId);
    return r ? buildPerspectives(r.sc, r.c.id, r.c.runId ?? "r_demo") : null;
  },

  async getEvidence(caseId) {
    await delay();
    const r = requireResults(caseId);
    return r ? buildEvidence(r.sc) : null;
  },

  async getCrossReview(caseId) {
    await delay();
    const r = requireResults(caseId);
    return r ? buildCrossReview(r.sc) : null;
  },

  async getSynthesis(caseId) {
    await delay();
    const r = requireResults(caseId);
    return r ? r.sc.synthesis : null;
  },

  async getReport(caseId) {
    await delay(280);
    const r = requireResults(caseId);
    if (!r) return null;
    return buildReport(r.sc, r.c.id, r.c.runId ?? "r_demo", r.c.updatedAt);
  },

  async getQuestions(caseId) {
    await delay();
    const r = requireResults(caseId);
    return r ? mergedQuestions(r.c, r.sc) : null;
  },

  async updateQuestion(caseId, questionId, patch) {
    await delay(80);
    const r = requireResults(caseId);
    if (!r) throw new Error("No questions for this case yet");
    const s = store();
    const prev = s.questionState[caseId]?.[questionId];
    const base = r.sc.questions.find((q) => q.id === questionId);
    if (!base) throw new Error("Question not found");
    s.questionState[caseId] = {
      ...(s.questionState[caseId] ?? {}),
      [questionId]: { status: patch.status ?? prev?.status ?? base.status, note: patch.note ?? prev?.note },
    };
    save();
    return mergedQuestions(r.c, r.sc).find((q) => q.id === questionId)!;
  },

  async getTrace(caseId, itemId) {
    await delay(180);
    const c = findCase(caseId);
    if (!c) return null;
    return buildTrace(scenarioFor(c), itemId);
  },

  async getSecondOpinion(caseId) {
    await delay(120);
    const c = findCase(caseId);
    return c ? secondOpinionState(c) : { status: "none" };
  },

  async submitSecondOpinion(caseId, file) {
    await delay(500);
    store().secondOpinion[caseId] = { startedAt: Date.now(), documentName: file.name };
    save();
    return { status: "processing", documentName: file.name };
  },

  async getComparison(caseId) {
    await delay(200);
    const r = requireResults(caseId);
    if (!r) return null;
    return secondOpinionState(r.c).status === "ready" ? r.sc.comparison : null;
  },
};

/**
 * Prototype-only controls. These exist so people can explore the demo (pick a
 * sample case, force a partial or failed run, skip the wait). They are NOT part
 * of the production-facing `AdvisorApi`; the UI reaches them only through
 * `src/lib/prototype.ts`, which is empty when a real backend is configured.
 */
export const prototypeControls: PrototypeControls = {
  listSampleCases(): SampleCase[] {
    return scenarioList.map((sc) => ({
      id: sc.id,
      title: scenarioBlurbs[sc.id].title,
      blurb: scenarioBlurbs[sc.id].blurb,
      ageYears: sc.seedCase.ageYears,
      sex: sc.seedCase.sex,
      documentCount: sc.documents.length,
    }));
  },

  async attachSampleRecords(caseId, scenario) {
    await delay(500);
    const sc = scenarios[scenario];
    const s = store();
    s.documents[caseId] = sc.documents.map((d) => ({ ...d }));
    patchCase(caseId, {
      scenario, title: sc.seedCase.title, ageYears: sc.seedCase.ageYears, sex: sc.seedCase.sex, specialtyLabel: sc.seedCase.specialtyLabel,
      documentCount: sc.documents.length,
    });
    return findCase(caseId)!;
  },

  setNextRunOutcome(caseId, outcome) {
    const s = store();
    if (outcome) s.pendingOutcome[caseId] = outcome;
    else delete s.pendingOutcome[caseId];
    save();
  },

  async skipToResults(runId) {
    const rec = store().runs[runId];
    if (rec) {
      rec.skipped = true;
      save();
    }
  },
};
