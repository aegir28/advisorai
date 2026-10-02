import { describe, expect, it } from "vitest";
import {
  AnalysisRunSchema,
  CaseV1Schema,
  ComparisonSchema,
  CrossReviewDataSchema,
  EvidenceDataSchema,
  PatientReportSchema,
  PerspectivesDataSchema,
  QuestionSchema,
  SpecialistReportSchema,
  SynthesisSchema,
  TimelineDataSchema,
  TraceSchema,
  DocumentItemSchema,
  FactSchema,
  CaseSummarySchema,
} from "@/domain/schemas";
import { buildCaseV1, buildCrossReview, buildEvidence, buildPerspectives, buildReport, buildTrace } from "@/mocks/builders";
import { mockApi } from "@/mocks/mock-api";
import { scenarioList } from "@/mocks/scenarios";

/**
 * The three synthetic scenarios are the contract's reference examples: every
 * fixture must satisfy the hardened schemas, and every ID must resolve.
 */
describe.each(scenarioList.map((sc) => [sc.id, sc] as const))("scenario %s", (_id, sc) => {
  const caseId = sc.seedCase.id;
  const runId = sc.seedCase.runId!;
  const report = buildReport(sc, caseId, runId, sc.seedCase.updatedAt);
  const allFactIds = new Set([...sc.facts, ...sc.secondOpinionFacts].map((f) => f.id));

  it("case summary, documents and facts conform", () => {
    expect(CaseSummarySchema.safeParse(sc.seedCase).success).toBe(true);
    for (const d of sc.documents) expect(DocumentItemSchema.safeParse(d).success, d.id).toBe(true);
    for (const f of [...sc.facts, ...sc.secondOpinionFacts]) expect(FactSchema.safeParse(f).success, f.id).toBe(true);
  });

  it("is a valid case.v1 and carries no identity", () => {
    const c = buildCaseV1(sc, caseId);
    const parsed = CaseV1Schema.safeParse(c);
    expect(parsed.success, parsed.success ? "" : JSON.stringify(parsed.error.issues)).toBe(true);
    expect(c.schema_version).toBe("case.v1");
    expect(c.case_id).toBe(caseId);
    // Names live in the app profile, never in the canonical case agents read.
    const owner = sc.seedCase.ownerLabel.split(" ")[0].replace(/\.$/, "");
    expect(JSON.stringify(c)).not.toContain(owner);
    expect(JSON.stringify(c)).not.toMatch(/ownerLabel|email|phone/i);
    // Every fact reference points at a real extracted fact.
    const refs = [
      ...c.symptoms, ...c.diagnoses, ...c.medications, ...c.recommendations, ...c.treatment_history,
      ...c.investigations.labs, ...c.investigations.imaging, ...c.investigations.ecg,
    ].map((x) => x.fact_ref);
    for (const r of refs) expect(allFactIds.has(r), r).toBe(true);
    expect(c.evidence_refs.length).toBe(sc.facts.length);
  });

  it("has valid specialist_report.v1 reports stamped with the real case and run", () => {
    const { reports } = buildPerspectives(sc, "c_other", "r_other");
    expect(reports.length).toBe(sc.specialists.length);
    for (const r of reports) {
      const parsed = SpecialistReportSchema.safeParse(r);
      expect(parsed.success, `${r.id}: ${parsed.success ? "" : JSON.stringify(parsed.error.issues)}`).toBe(true);
      expect(r.schema_version).toBe("specialist_report.v1");
      expect(r.case_id).toBe("c_other");
      expect(r.run_id).toBe("r_other");
      // Complete reports must actually say something.
      if (r.status === "complete") expect(r.findings.length).toBeGreaterThan(0);
      // Finding references resolve.
      for (const f of [...r.findings, ...r.considerations]) {
        for (const ref of f.factRefs) expect(allFactIds.has(ref), `${r.id}/${f.id}/${ref}`).toBe(true);
        for (const sid of f.sourceIds ?? []) expect(sc.sources.some((s) => s.id === sid), sid).toBe(true);
      }
      for (const e of r.evidence_refs) expect(sc.sources.some((s) => s.id === e.sourceId), e.sourceId).toBe(true);
    }
    expect(PerspectivesDataSchema.safeParse(buildPerspectives(sc, caseId, runId)).success).toBe(true);
  });

  it("has a valid report.v1 with the 19 sections", () => {
    const parsed = PatientReportSchema.safeParse(report);
    expect(parsed.success, parsed.success ? "" : JSON.stringify(parsed.error.issues)).toBe(true);
    expect(report.schema_version).toBe("report.v1");
    expect(report.sections.map((s) => s.number)).toEqual(Array.from({ length: 19 }, (_, i) => i + 1));
  });

  it("traces every report claim to a valid trace.v1 that ends at a document page", () => {
    const ids = new Set(report.sections.flatMap((s) => s.items.flatMap((i) => i.evidenceIds)));
    expect(ids.size).toBeGreaterThan(10);
    for (const id of ids) {
      const trace = buildTrace(sc, id);
      expect(trace, `no trace for ${id}`).not.toBeNull();
      const parsed = TraceSchema.safeParse(trace);
      expect(parsed.success, `${id}: ${parsed.success ? "" : JSON.stringify(parsed.error.issues)}`).toBe(true);
      expect(trace!.schema_version).toBe("trace.v1");
    }
    // Patient-fact statements must reach a source document page.
    const syn = buildTrace(sc, sc.reportPlan.s2[0])!;
    expect(JSON.stringify(syn)).toContain('"docId"');
  });

  it("resolves every ID referenced by synthesis, claims, questions, matrix, highlights and comparison", () => {
    for (const item of sc.synthesis.items) {
      expect(buildTrace(sc, item.id), item.id).not.toBeNull();
      for (const d of item.derivedFrom) expect(buildTrace(sc, d), `${item.id} -> ${d}`).not.toBeNull();
    }
    for (const c of sc.claims) {
      for (const f of c.patientFactIds) expect(allFactIds.has(f), `${c.id} -> ${f}`).toBe(true);
      for (const s of c.externalSourceIds) expect(sc.sources.some((x) => x.id === s), `${c.id} -> ${s}`).toBe(true);
    }
    for (const q of sc.questions) {
      expect(QuestionSchema.safeParse(q).success, q.id).toBe(true);
      for (const l of q.linkedItemIds) expect(buildTrace(sc, l), `${q.id} -> ${l}`).not.toBeNull();
    }
    for (const row of sc.matrix) for (const id of row.itemIds) expect(buildTrace(sc, id), `${row.id} -> ${id}`).not.toBeNull();
    for (const h of sc.highlights) expect(buildTrace(sc, h.id), h.id).not.toBeNull();
    for (const row of sc.comparison.rows) {
      for (const id of [...row.evidenceA, ...row.evidenceB, ...row.itemIds]) expect(buildTrace(sc, id), `${row.id} -> ${id}`).not.toBeNull();
    }
    for (const a of sc.comparison.answeredByOpinion) expect(sc.questions.some((q) => q.id === a.questionId), a.questionId).toBe(true);
  });

  it("timeline, evidence, cross-review, synthesis and comparison conform", () => {
    expect(TimelineDataSchema.safeParse(sc.timeline).success).toBe(true);
    expect(EvidenceDataSchema.safeParse(buildEvidence(sc)).success).toBe(true);
    expect(CrossReviewDataSchema.safeParse(buildCrossReview(sc)).success).toBe(true);
    expect(SynthesisSchema.safeParse(sc.synthesis).success).toBe(true);
    expect(ComparisonSchema.safeParse(sc.comparison).success).toBe(true);
  });

  it("keeps uncertainty visible: flagged synthesis items reach the report", () => {
    const flagged = sc.synthesis.items.filter((i) => i.flag).map((i) => i.id);
    expect(flagged.length).toBeGreaterThan(0);
    const inReport = new Set(report.sections.flatMap((s) => s.items.map((i) => i.id)));
    expect(flagged.some((id) => inReport.has(id))).toBe(true);
  });

  it("has a valid run.v1 for the seeded analysis", async () => {
    const run = await mockApi.getRun(runId);
    expect(run).not.toBeNull();
    const parsed = AnalysisRunSchema.safeParse(run);
    expect(parsed.success, parsed.success ? "" : JSON.stringify(parsed.error.issues)).toBe(true);
    expect(run!.schema_version).toBe("run.v1");
    expect(run!.status).toBe(sc.finalStatus);
    expect(run!.steps).toHaveLength(14);
  });
});

describe("scenario coverage", () => {
  it("includes the three required synthetic cases, two of them hard", () => {
    expect(scenarioList.map((s) => s.id).sort()).toEqual(["cardiology", "conflicting", "missing_info"]);
  });
  it("hard cases keep gaps and disagreement visible in their data", () => {
    const missing = scenarioList.find((s) => s.id === "missing_info")!;
    expect(missing.specialists.some((r) => r.status !== "complete")).toBe(true);
    expect(missing.documents.some((d) => d.status === "needs_attention")).toBe(true);
    const conflicting = scenarioList.find((s) => s.id === "conflicting")!;
    expect(conflicting.claims.some((c) => c.status === "contradicted")).toBe(true);
    expect(conflicting.matrix.some((m) => m.relationship === "disagreement")).toBe(true);
  });
});
