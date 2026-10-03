/**
 * Wire casing adapter (ADR 0001).
 *
 * The backend wire contracts are snake_case throughout. The frontend domain model keeps the
 * camelCase names the Phase 1 UI already uses for some fields (`factRefs`, `routingReason`, ...)
 * and the snake_case names it already uses for others (`schema_version`, `run_id`, `fact_ref`, ...).
 *
 * So the conversion is an EXPLICIT table, not a blanket camelCase<->snake_case rule: a blanket
 * rule would rename the domain's existing snake_case fields and break the UI. A key not in the
 * table passes through unchanged. The backend rejects unknown keys (`extra="forbid"`), and the
 * contract tests round-trip every fixture, so a missing entry fails a test instead of shipping.
 */

/** domain (camelCase) key -> wire (snake_case) key, for the five versioned contracts. */
export const DOMAIN_TO_WIRE: Readonly<Record<string, string>> = {
  // SourceRef
  docId: "doc_id",
  // Finding, Uncertainty, MissingInfo, SpecialistQuestion, EvidenceRef
  factRefs: "fact_refs",
  sourceIds: "source_ids",
  resolvableBy: "resolvable_by",
  whyItMatters: "why_it_matters",
  linkedTo: "linked_to",
  sourceId: "source_id",
  // SpecialistReport
  routingReason: "routing_reason",
  statusNote: "status_note",
  // PatientReport, ReportSection, ReportItem
  caseId: "case_id",
  runId: "run_id",
  generatedAt: "generated_at",
  questionAudience: "question_audience",
  evidenceIds: "evidence_ids",
  // AnalysisRun
  startedAt: "started_at",
  finishedAt: "finished_at",
  // Trace
  itemId: "item_id",
  externalSource: "external_source",
  // AI output shapes (evidence/claims, synthesis, questions, comparison, routing): no endpoint serves them yet,
  // but the backend models exist (backend/app/schemas) and the fixture exporter needs their wire spelling.
  patientFactIds: "patient_fact_ids",
  externalSourceIds: "external_source_ids",
  removalReason: "removal_reason",
  derivedFrom: "derived_from",
  escalationReason: "escalation_reason",
  linkedItemIds: "linked_item_ids",
  itemIds: "item_ids",
  opinionALabel: "opinion_a_label",
  opinionBLabel: "opinion_b_label",
  opinionA: "opinion_a",
  opinionB: "opinion_b",
  evidenceA: "evidence_a",
  evidenceB: "evidence_b",
  nextQuestions: "next_questions",
  answeredByOpinion: "answered_by_opinion",
  questionId: "question_id",
  notSelected: "not_selected",
  missingForRouting: "missing_for_routing",
};

/**
 * The domain model is not uniform: `caseId` / `runId` are camelCase in the report and run models
 * but `case_id` / `run_id` are already snake_case in `case.v1` and `specialist_report.v1`. So the
 * wire -> domain direction depends on the contract. These wire keys stay as they are in the domain
 * for the listed contract (domain -> wire is unambiguous and needs no context).
 */
export type WireContract = "case.v1" | "specialist_report.v1" | "report.v1" | "trace.v1" | "run.v1";

const KEPT_AS_WIRE: Readonly<Record<WireContract, readonly string[]>> = {
  "case.v1": ["case_id"],
  "specialist_report.v1": ["case_id", "run_id"],
  "report.v1": [],
  "trace.v1": [],
  "run.v1": [],
};

function wireToDomain(contract: WireContract): Readonly<Record<string, string>> {
  const kept = new Set(KEPT_AS_WIRE[contract]);
  return Object.fromEntries(
    Object.entries(DOMAIN_TO_WIRE)
      .filter(([, wire]) => !kept.has(wire))
      .map(([domain, wire]) => [wire, domain]),
  );
}

/** Keys whose value is free-form data: its inner keys are content, never renamed. */
const OPAQUE_KEYS: ReadonlySet<string> = new Set(["extensions", "meta"]);

function mapKeys(value: unknown, table: Readonly<Record<string, string>>): unknown {
  if (Array.isArray(value)) return value.map((v) => mapKeys(v, table));
  if (value === null || typeof value !== "object") return value;
  const out: Record<string, unknown> = {};
  for (const [key, inner] of Object.entries(value)) {
    out[table[key] ?? key] = OPAQUE_KEYS.has(key) ? inner : mapKeys(inner, table);
  }
  return out;
}

/** Domain model -> wire form (what the backend sends and accepts). */
export function toWire(domain: unknown): unknown {
  return mapKeys(domain, DOMAIN_TO_WIRE);
}

/** Wire form -> domain model (what the UI consumes). Validate the result with the Zod schema. */
export function fromWire(wire: unknown, contract: WireContract): unknown {
  return mapKeys(wire, wireToDomain(contract));
}

const SNAKE_CASE = /^[a-z][a-z0-9]*(_[a-z0-9]+)*$/;

/**
 * Every key that is not inside a free-form (`extensions` / `meta`) subtree.
 * Used by tests to prove a wire payload is snake_case throughout.
 */
export function wireKeys(value: unknown, into: string[] = []): string[] {
  if (Array.isArray(value)) {
    for (const v of value) wireKeys(v, into);
  } else if (value !== null && typeof value === "object") {
    for (const [key, inner] of Object.entries(value)) {
      into.push(key);
      if (!OPAQUE_KEYS.has(key)) wireKeys(inner, into);
    }
  }
  return into;
}

export function isSnakeCase(key: string): boolean {
  return SNAKE_CASE.test(key);
}
