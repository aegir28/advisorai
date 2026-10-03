import { fileURLToPath } from "node:url";
import { describe, it, expect } from "vitest";
import { buildCrossReview, buildEvidence, buildPerspectives } from "@/mocks/builders";
import { scenarioList } from "@/mocks/scenarios";
import { toWire } from "@/lib/api/http/casing";

/**
 * Exports the shapes the AI steps will produce (evidence/claims, cross-review, routing plan, synthesis, questions,
 * second-opinion comparison) from the three synthetic scenarios, as WIRE-form JSON. The backend's contract tests
 * (backend/tests/contract/test_ai_output_shapes.py) validate them with its Pydantic models, so an AI step that
 * returns the backend model is, by construction, something the UI can already render.
 *
 *   npm run export:fixtures   regenerates the files (vitest -u)
 *   npm test                  fails if they drift from the scenarios
 *
 * Synthetic and fictional: no real patient data.
 */
const FIXTURE_ROOT = fileURLToPath(new URL("../../../../backend/tests/fixtures/contracts/", import.meta.url));
const json = (value: unknown) => `${JSON.stringify(toWire(value), null, 2)}\n`;

describe.each(scenarioList.map((sc) => [sc.id, sc] as const))("AI output shapes: %s", (_id, sc) => {
  const dir = `${FIXTURE_ROOT}${sc.id}/`;
  const caseId = sc.seedCase.id;
  const runId = sc.seedCase.runId!;

  it("evidence", async () => {
    await expect(json(buildEvidence(sc))).toMatchFileSnapshot(`${dir}evidence.json`);
  });
  it("cross_review", async () => {
    await expect(json(buildCrossReview(sc))).toMatchFileSnapshot(`${dir}cross_review.json`);
  });
  it("routing_plan", async () => {
    await expect(json(buildPerspectives(sc, caseId, runId).routing)).toMatchFileSnapshot(`${dir}routing_plan.json`);
  });
  it("synthesis", async () => {
    await expect(json(sc.synthesis)).toMatchFileSnapshot(`${dir}synthesis.json`);
  });
  it("questions", async () => {
    await expect(json(sc.questions)).toMatchFileSnapshot(`${dir}questions.json`);
  });
  it("comparison", async () => {
    await expect(json(sc.comparison)).toMatchFileSnapshot(`${dir}comparison.json`);
  });
});
