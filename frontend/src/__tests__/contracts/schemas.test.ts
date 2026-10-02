import { describe, expect, it } from "vitest";
import {
  AnalysisRunSchema,
  CaseV1Schema,
  PatientReportSchema,
  SCHEMA_VERSIONS,
  SpecialistReportSchema,
  TraceSchema,
} from "@/domain/schemas";
import { buildCaseV1, buildPerspectives, buildReport, buildTrace } from "@/mocks/builders";
import { scenarios } from "@/mocks/scenarios";

/**
 * Negative tests: the contracts must REJECT malformed data. Each test starts
 * from a valid fixture-derived object and breaks exactly one thing.
 */
const sc = scenarios.cardiology;
const validReport = () => structuredClone(buildReport(sc, "c_9f2", "r_77", "2026-10-02T09:12:00Z"));
const validSpecialist = () => structuredClone(buildPerspectives(sc, "c_9f2", "r_77").reports[0]);
const validCase = () => structuredClone(buildCaseV1(sc, "c_9f2"));
const validTrace = () => structuredClone(buildTrace(sc, "syn_8")!);
const validRun = () => ({
  schema_version: SCHEMA_VERSIONS.run,
  id: "r_1",
  caseId: "c_1",
  status: "complete" as const,
  progress: 1,
  steps: Array.from({ length: 14 }, (_, i) => ({ n: i + 1, status: "done" as const })),
  startedAt: "2026-10-02T09:00:00Z",
  finishedAt: "2026-10-02T09:04:00Z",
  warnings: [] as string[],
});

describe("schema versions", () => {
  it("uses exactly the five agreed version names", () => {
    expect(SCHEMA_VERSIONS).toEqual({
      case: "case.v1",
      specialistReport: "specialist_report.v1",
      report: "report.v1",
      trace: "trace.v1",
      run: "run.v1",
    });
  });
});

describe("case.v1", () => {
  it("accepts a valid case", () => expect(CaseV1Schema.safeParse(validCase()).success).toBe(true));
  it("rejects a wrong schema_version", () => {
    expect(CaseV1Schema.safeParse({ ...validCase(), schema_version: "case.v2" }).success).toBe(false);
  });
  it("rejects a missing schema_version", () => {
    const { schema_version: _omit, ...rest } = validCase();
    void _omit;
    expect(CaseV1Schema.safeParse(rest).success).toBe(false);
  });
  it("rejects an invalid sex or age", () => {
    expect(CaseV1Schema.safeParse({ ...validCase(), demographics: { age: 52, sex: "Z" } }).success).toBe(false);
    expect(CaseV1Schema.safeParse({ ...validCase(), demographics: { age: -1, sex: "M" } }).success).toBe(false);
  });
  it("rejects a fact without a fact_ref", () => {
    const c = validCase();
    c.symptoms[0] = { ...c.symptoms[0], fact_ref: "" };
    expect(CaseV1Schema.safeParse(c).success).toBe(false);
  });
});

describe("specialist_report.v1", () => {
  it("accepts a valid report", () => expect(SpecialistReportSchema.safeParse(validSpecialist()).success).toBe(true));

  it.each(["schema_version", "run_id", "case_id", "missing_info", "questions", "evidence_refs", "findings", "uncertainties", "contradictions", "considerations", "confidence", "limitations", "specialist"])(
    "rejects a report missing `%s`",
    (field) => {
      const r = validSpecialist() as unknown as Record<string, unknown>;
      delete r[field];
      expect(SpecialistReportSchema.safeParse(r).success).toBe(false);
    },
  );

  it("rejects a wrong schema_version", () => {
    expect(SpecialistReportSchema.safeParse({ ...validSpecialist(), schema_version: "specialist_report.v2" }).success).toBe(false);
  });
  it("rejects an unknown specialty and a finding with a bad kind", () => {
    expect(SpecialistReportSchema.safeParse({ ...validSpecialist(), specialist: "astrology" }).success).toBe(false);
    const r = validSpecialist();
    r.findings[0] = { ...r.findings[0], kind: "opinion" as never };
    expect(SpecialistReportSchema.safeParse(r).success).toBe(false);
  });
  it("allows extensions to carry specialty-specific data", () => {
    expect(SpecialistReportSchema.safeParse({ ...validSpecialist(), extensions: { cardiology: { risk_scores_mentioned: [] } } }).success).toBe(true);
  });
});

describe("report.v1", () => {
  it("accepts a valid report", () => expect(PatientReportSchema.safeParse(validReport()).success).toBe(true));
  it("rejects a wrong schema_version", () => {
    expect(PatientReportSchema.safeParse({ ...validReport(), schema_version: "report.v2" }).success).toBe(false);
  });
  it("rejects a report that does not have exactly the 19 sections", () => {
    const r = validReport();
    r.sections = r.sections.slice(0, 18);
    expect(PatientReportSchema.safeParse(r).success).toBe(false);
  });
  it("rejects sections that are out of order", () => {
    const r = validReport();
    [r.sections[0], r.sections[1]] = [r.sections[1], r.sections[0]];
    expect(PatientReportSchema.safeParse(r).success).toBe(false);
  });
  it("rejects a non-template sentence with no id (every claim must be traceable)", () => {
    const r = validReport();
    r.sections[0].items[0] = { ...r.sections[0].items[0], id: undefined };
    expect(PatientReportSchema.safeParse(r).success).toBe(false);
  });
  it("rejects a non-template sentence with no evidence", () => {
    const r = validReport();
    r.sections[0].items[0] = { ...r.sections[0].items[0], evidenceIds: [] };
    expect(PatientReportSchema.safeParse(r).success).toBe(false);
  });
  it("allows fixed template text without an id", () => {
    const r = validReport();
    r.sections[18].items = [{ text: "Fixed notice", kind: "template", evidenceIds: [] }];
    expect(PatientReportSchema.safeParse(r).success).toBe(true);
  });
});

describe("trace.v1", () => {
  it("accepts a valid trace", () => expect(TraceSchema.safeParse(validTrace()).success).toBe(true));
  it("rejects a wrong or missing schema_version", () => {
    expect(TraceSchema.safeParse({ ...validTrace(), schema_version: "trace.v2" }).success).toBe(false);
    const { schema_version: _omit, ...rest } = validTrace();
    void _omit;
    expect(TraceSchema.safeParse(rest).success).toBe(false);
  });
  it("validates nested nodes recursively", () => {
    const t = validTrace();
    t.root.children[0].children[0] = { ...t.root.children[0].children[0], level: "nonsense" as never };
    expect(TraceSchema.safeParse(t).success).toBe(false);
  });
  it("rejects a source with a non-positive page", () => {
    const t = validTrace();
    const leaf = JSON.stringify(t).includes('"source"');
    expect(leaf).toBe(true);
    const bad = JSON.parse(JSON.stringify(t).replace(/"page":\d+/, '"page":0'));
    expect(TraceSchema.safeParse(bad).success).toBe(false);
  });
});

describe("run.v1", () => {
  it("accepts a valid run", () => expect(AnalysisRunSchema.safeParse(validRun()).success).toBe(true));
  it("rejects a wrong or missing schema_version", () => {
    expect(AnalysisRunSchema.safeParse({ ...validRun(), schema_version: "run.v2" }).success).toBe(false);
    const { schema_version: _omit, ...rest } = validRun();
    void _omit;
    expect(AnalysisRunSchema.safeParse(rest).success).toBe(false);
  });
  it("rejects a run that does not have exactly 14 ordered steps", () => {
    const r = validRun();
    r.steps = r.steps.slice(0, 13);
    expect(AnalysisRunSchema.safeParse(r).success).toBe(false);
  });
  it("rejects a failed run that does not explain itself", () => {
    expect(AnalysisRunSchema.safeParse({ ...validRun(), status: "failed" }).success).toBe(false);
    expect(AnalysisRunSchema.safeParse({ ...validRun(), status: "failed", failure: { title: "Stopped", body: "Why" } }).success).toBe(true);
  });
  it("rejects progress outside 0..1", () => {
    expect(AnalysisRunSchema.safeParse({ ...validRun(), progress: 1.5 }).success).toBe(false);
  });
});
