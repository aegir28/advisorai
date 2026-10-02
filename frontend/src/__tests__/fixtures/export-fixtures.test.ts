import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildCaseV1, buildPerspectives, buildReport, buildTrace } from "@/mocks/builders";
import { mockApi } from "@/mocks/mock-api";
import { scenarioList } from "@/mocks/scenarios";
import { toWire } from "@/lib/api/http/casing";
import { CONTRACT_SHAPES } from "./contract-shape";

/**
 * Exports the three synthetic scenarios as WIRE-form (snake_case) JSON fixtures that the backend's
 * contract tests validate with its Pydantic models.
 *
 * This file is both the exporter and the drift guard:
 *
 *   npm run export:fixtures   regenerates backend/tests/fixtures/contracts/** (vitest -u)
 *   npm test                  fails if the checked-in fixtures differ from what the scenarios
 *                             produce today (and in CI, a missing fixture also fails)
 *
 * The fixtures are synthetic and fictional: no real patient data.
 */
const FIXTURE_ROOT = fileURLToPath(new URL("../../../../backend/tests/fixtures/contracts/", import.meta.url));

const json = (value: unknown) => `${JSON.stringify(toWire(value), null, 2)}\n`;

describe.each(scenarioList.map((sc) => [sc.id, sc] as const))("wire fixtures: %s", (_id, sc) => {
  const caseId = sc.seedCase.id;
  const runId = sc.seedCase.runId!;
  const report = buildReport(sc, caseId, runId, sc.seedCase.updatedAt);
  const dir = `${FIXTURE_ROOT}${sc.id}/`;

  it("case.v1", async () => {
    await expect(json(buildCaseV1(sc, caseId))).toMatchFileSnapshot(`${dir}case.v1.json`);
  });

  it("specialist_report.v1", async () => {
    await expect(json(buildPerspectives(sc, caseId, runId).reports)).toMatchFileSnapshot(`${dir}specialist_reports.v1.json`);
  });

  it("report.v1", async () => {
    await expect(json(report)).toMatchFileSnapshot(`${dir}report.v1.json`);
  });

  it("trace.v1 (every ID the report cites)", async () => {
    const ids = [...new Set(report.sections.flatMap((s) => s.items.flatMap((i) => i.evidenceIds)))].sort();
    const traces = ids.map((id) => buildTrace(sc, id));
    expect(traces.every((t) => t !== null)).toBe(true);
    await expect(json(traces)).toMatchFileSnapshot(`${dir}traces.v1.json`);
  });

  it("run.v1", async () => {
    await expect(json(await mockApi.getRun(runId))).toMatchFileSnapshot(`${dir}run.v1.json`);
  });
});

describe("contract shape", () => {
  it("exports field paths and optionality of the five contracts, read from the Zod schemas", async () => {
    await expect(`${JSON.stringify(CONTRACT_SHAPES, null, 2)}
`).toMatchFileSnapshot(`${FIXTURE_ROOT}contract-shapes.json`);
  });
});
