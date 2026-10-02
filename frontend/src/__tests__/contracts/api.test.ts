import { describe, expect, it } from "vitest";
import { api, ContractError } from "@/lib/api";
import type { AdvisorApi } from "@/lib/api/types";
import { RESPONSE_SCHEMAS, withValidation } from "@/lib/api/validate";
import { buildReport } from "@/mocks/builders";
import { mockApi, prototypeControls } from "@/mocks/mock-api";
import { scenarios } from "@/mocks/scenarios";

/**
 * The API boundary: the production contract is free of mock-only members, and
 * every response is validated before it can reach a screen.
 */
describe("AdvisorApi production contract", () => {
  it("contains no mock-only members", () => {
    const keys = Object.keys(mockApi);
    expect(keys).not.toContain("attachSampleRecords");
    expect(keys).not.toContain("skipToResults");
    // startAnalysis takes only the case ID: no `simulate` option.
    expect(mockApi.startAnalysis.length).toBe(1);
  });

  it("keeps demo controls in a separate prototype-only object", () => {
    expect(Object.keys(prototypeControls).sort()).toEqual(["attachSampleRecords", "listSampleCases", "setNextRunOutcome", "skipToResults"]);
    expect(prototypeControls.listSampleCases().map((s) => s.id).sort()).toEqual(["cardiology", "conflicting", "missing_info"]);
  });

  it("declares a response schema for every method that returns data", () => {
    const voidMethods = ["deleteCase", "removeDocument"];
    for (const key of Object.keys(mockApi)) {
      if (voidMethods.includes(key)) continue;
      expect(RESPONSE_SCHEMAS, key).toHaveProperty(key);
    }
  });
});

describe("validated api: every read method passes for every seeded case", () => {
  for (const sc of Object.values(scenarios)) {
    it(`${sc.id}`, async () => {
      const id = sc.seedCase.id;
      expect((await api.listCases()).length).toBeGreaterThanOrEqual(3);
      expect(await api.getCase(id)).not.toBeNull();
      expect(await api.getCaseOverview(id)).not.toBeNull();
      expect((await api.getDocuments(id)).length).toBe(sc.documents.length);
      expect((await api.getRun(sc.seedCase.runId!))!.schema_version).toBe("run.v1");
      expect(await api.getTimeline(id)).not.toBeNull();
      expect((await api.getPerspectives(id))!.reports.every((r) => r.case_id === id && r.run_id === sc.seedCase.runId)).toBe(true);
      expect(await api.getEvidence(id)).not.toBeNull();
      expect(await api.getCrossReview(id)).not.toBeNull();
      expect(await api.getSynthesis(id)).not.toBeNull();
      expect((await api.getReport(id))!.schema_version).toBe("report.v1");
      expect((await api.getQuestions(id))!.length).toBe(sc.questions.length);
      expect((await api.getTrace(id, sc.reportPlan.s1[0]))!.schema_version).toBe("trace.v1");
      expect(await api.getTrace(id, "does_not_exist")).toBeNull();
      expect((await api.getSecondOpinion(id)).status).toBe("none");
      expect(await api.getComparison(id)).toBeNull();
    });
  }
});

describe("validated api: run states stay valid", () => {
  it.each([
    ["complete", "complete"],
    ["partial", "partial"],
    ["failed", "failed"],
  ] as const)("a %s run validates and ends as %s", async (outcome, expected) => {
    const created = await api.createCase({ concern: "Contract test case", ageYears: 40, sex: "F" });
    await prototypeControls.attachSampleRecords(created.id, "cardiology");
    prototypeControls.setNextRunOutcome(created.id, outcome);
    const { runId } = await api.startAnalysis(created.id);

    const running = await api.getRun(runId);
    expect(running!.status).toBe("running");
    expect(running!.steps).toHaveLength(14);

    await prototypeControls.skipToResults(runId);
    const done = await api.getRun(runId);
    expect(done!.status).toBe(expected);
    if (expected === "failed") expect(done!.failure).toBeDefined();
    if (expected === "partial") expect(done!.warnings.length).toBeGreaterThan(0);
  });

  it("a case created from scratch has its perspectives re-stamped with its own IDs", async () => {
    const created = await api.createCase({ concern: "Another contract test", ageYears: 52, sex: "M" });
    await prototypeControls.attachSampleRecords(created.id, "cardiology");
    const { runId } = await api.startAnalysis(created.id);
    await prototypeControls.skipToResults(runId);
    await api.getRun(runId); // settles the case
    const p = await api.getPerspectives(created.id);
    expect(p!.reports.every((r) => r.case_id === created.id && r.run_id === runId)).toBe(true);
  });
});

describe("validation rejects malformed responses before they reach the UI", () => {
  const broken = (overrides: Partial<AdvisorApi>): AdvisorApi => withValidation({ ...mockApi, ...overrides } as AdvisorApi);
  const goodReport = () => buildReport(scenarios.cardiology, "c_9f2", "r_77", "2026-10-02T09:12:00Z");

  it("rejects a report with the wrong number of sections", async () => {
    const bad = broken({ getReport: async () => ({ ...goodReport(), sections: goodReport().sections.slice(0, 5) }) });
    await expect(bad.getReport("c_9f2")).rejects.toBeInstanceOf(ContractError);
  });

  it("rejects a report missing its schema_version", async () => {
    const { schema_version: _omit, ...rest } = goodReport();
    void _omit;
    const bad = broken({ getReport: async () => rest as never });
    await expect(bad.getReport("c_9f2")).rejects.toThrow(/getReport\(\) does not match its contract/);
  });

  it("rejects a specialist report without run_id", async () => {
    const bad = broken({
      getPerspectives: async () => {
        const p = await mockApi.getPerspectives("c_9f2");
        const { run_id: _omit, ...first } = p!.reports[0];
        void _omit;
        return { ...p!, reports: [first as never, ...p!.reports.slice(1)] };
      },
    });
    await expect(bad.getPerspectives("c_9f2")).rejects.toBeInstanceOf(ContractError);
  });

  it("rejects a run with an unknown status and a malformed question", async () => {
    const badRun = broken({ getRun: async () => ({ ...(await mockApi.getRun("r_77"))!, status: "exploded" as never }) });
    await expect(badRun.getRun("r_77")).rejects.toBeInstanceOf(ContractError);
    const badQ = broken({ getQuestions: async () => [{ id: "q1", text: "", priority: 9 }] as never });
    await expect(badQ.getQuestions("c_9f2")).rejects.toBeInstanceOf(ContractError);
  });

  it("passes valid data through untouched", async () => {
    const ok = broken({});
    expect((await ok.getReport("c_9f2"))!.sections).toHaveLength(19);
  });
});
