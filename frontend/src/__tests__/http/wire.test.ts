import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildCaseV1, buildPerspectives, buildReport, buildTrace } from "@/mocks/builders";
import { mockApi } from "@/mocks/mock-api";
import { scenarioList } from "@/mocks/scenarios";
import { DOMAIN_TO_WIRE, fromWire, isSnakeCase, toWire, wireKeys } from "@/lib/api/http/casing";
import { decodeCase, decodeReport, decodeRun, decodeSpecialistReport, decodeTrace } from "@/lib/api/http/wire";

const FIXTURES = fileURLToPath(new URL("../../../../backend/tests/fixtures/contracts/", import.meta.url));
const fixture = (scenario: string, file: string): unknown => JSON.parse(readFileSync(`${FIXTURES}${scenario}/${file}`, "utf8"));

describe("wire casing adapter (ADR 0001)", () => {
  it("has no duplicate wire names", () => {
    const wire = Object.values(DOMAIN_TO_WIRE);
    expect(new Set(wire).size).toBe(wire.length);
    for (const w of wire) expect(isSnakeCase(w), w).toBe(true);
  });

  it("leaves free-form `extensions` and `meta` content untouched", () => {
    const value = { extensions: { camelCaseKey: { innerKey: 1 } }, sections: [{ items: [{ evidenceIds: ["a"], meta: { someLabel: "x" } }] }] };
    expect(toWire(value)).toEqual({
      extensions: { camelCaseKey: { innerKey: 1 } },
      sections: [{ items: [{ evidence_ids: ["a"], meta: { someLabel: "x" } }] }],
    });
  });

  it("does not rename the domain's own snake_case fields", () => {
    expect(toWire({ schema_version: "run.v1", run_id: "r", fact_ref: "f" })).toEqual({ schema_version: "run.v1", run_id: "r", fact_ref: "f" });
    expect(fromWire({ schema_version: "case.v1", case_id: "c", fact_ref: "f" }, "case.v1")).toEqual({ schema_version: "case.v1", case_id: "c", fact_ref: "f" });
  });

  it("maps case_id / run_id per contract: camelCase in report and run, unchanged in case and specialist report", () => {
    expect(fromWire({ case_id: "c", run_id: "r" }, "report.v1")).toEqual({ caseId: "c", runId: "r" });
    expect(fromWire({ case_id: "c" }, "run.v1")).toEqual({ caseId: "c" });
    expect(fromWire({ case_id: "c", run_id: "r" }, "specialist_report.v1")).toEqual({ case_id: "c", run_id: "r" });
    expect(fromWire({ case_id: "c" }, "case.v1")).toEqual({ case_id: "c" });
  });
});

describe.each(scenarioList.map((sc) => [sc.id, sc] as const))("wire round trip: %s", (_id, sc) => {
  const caseId = sc.seedCase.id;
  const runId = sc.seedCase.runId!;
  const report = buildReport(sc, caseId, runId, sc.seedCase.updatedAt);
  const strip = (v: unknown) => JSON.parse(JSON.stringify(v)); // drop `undefined`, as JSON does

  it("every contract encodes to snake_case only and decodes back to the same domain object", async () => {
    const run = await mockApi.getRun(runId);
    const cases: [string, unknown, (w: unknown) => unknown][] = [
      ["case.v1", buildCaseV1(sc, caseId), decodeCase],
      ["report.v1", report, decodeReport],
      ["run.v1", run, decodeRun],
      ["trace.v1", buildTrace(sc, sc.reportPlan.s2[0]), decodeTrace],
      ...buildPerspectives(sc, caseId, runId).reports.map((r): [string, unknown, (w: unknown) => unknown] => [`specialist_report.v1/${r.id}`, r, decodeSpecialistReport]),
    ];
    for (const [name, domain, decode] of cases) {
      const wire = toWire(domain);
      expect(wireKeys(wire).filter((k) => !isSnakeCase(k)), `${name}: non-snake_case wire keys`).toEqual([]);
      expect(decode(wire), name).toEqual(strip(domain));
    }
  });

  it("decodes the checked-in backend fixtures with the Zod schemas", () => {
    expect(decodeCase(fixture(sc.id, "case.v1.json")).case_id).toBe(caseId);
    expect(decodeReport(fixture(sc.id, "report.v1.json")).sections).toHaveLength(19);
    expect(decodeRun(fixture(sc.id, "run.v1.json")).steps).toHaveLength(14);
    for (const r of fixture(sc.id, "specialist_reports.v1.json") as unknown[]) expect(decodeSpecialistReport(r).run_id).toBe(runId);
    for (const t of fixture(sc.id, "traces.v1.json") as unknown[]) expect(decodeTrace(t).schema_version).toBe("trace.v1");
  });
});

describe("decoders reject bad wire payloads", () => {
  it("rejects a camelCase leak, a missing version and a broken rule", () => {
    const run = toWire({ schema_version: "run.v1", id: "r", caseId: "c", status: "complete", progress: 1, steps: [], startedAt: "2026-10-02", warnings: [] });
    expect(() => decodeRun(run)).toThrow(); // 0 steps
    const good = fixture("cardiology", "run.v1.json") as Record<string, unknown>;
    expect(() => decodeRun({ ...good, schema_version: "run.v2" })).toThrow();
    expect(() => decodeRun({ ...good, status: "failed" })).toThrow(); // failed without `failure`
    const { schema_version: _omit, ...noVersion } = good;
    void _omit;
    expect(() => decodeRun(noVersion)).toThrow();
  });
});
