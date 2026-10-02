import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { decodeCase, decodeReport, decodeRun, decodeSpecialistReport, decodeTrace } from "@/lib/api/http/wire";
import { scenarioList } from "@/mocks/scenarios";
import { CONTRACT_SHAPES } from "../fixtures/contract-shape";

/**
 * The Zod half of the Zod <-> Pydantic null parity (the backend proves the Pydantic half in
 * backend/tests/contract/test_optional_null_parity.py): for EVERY optional field of every
 * versioned contract, an absent key decodes and an explicit `null` is rejected.
 */
const FIXTURES = fileURLToPath(new URL("../../../../backend/tests/fixtures/contracts/", import.meta.url));
const read = (scenario: string, file: string): unknown => JSON.parse(readFileSync(`${FIXTURES}${scenario}/${file}`, "utf8"));

const CONTRACTS: Record<string, { file: string; decode: (wire: unknown) => unknown }> = {
  "case.v1": { file: "case.v1.json", decode: decodeCase },
  "specialist_report.v1": { file: "specialist_reports.v1.json", decode: decodeSpecialistReport },
  "report.v1": { file: "report.v1.json", decode: decodeReport },
  "trace.v1": { file: "traces.v1.json", decode: decodeTrace },
  "run.v1": { file: "run.v1.json", decode: decodeRun },
};

/** `id` is optional only for fixed template text, so dropping it from a claim is invalid. */
const CONDITIONALLY_REQUIRED = new Set(["report.v1:sections[].items[].id"]);

type Step = { key: string; list: boolean };
const parse = (path: string): Step[] => path.split(".").map((p) => ({ key: p.replace(/\[\]$/, ""), list: p.endsWith("[]") }));

/** Set the key to null (or delete it) on every object reached by the path. True if it reached any. */
function apply(node: unknown, steps: Step[], action: "null" | "absent"): boolean {
  if (node === null || typeof node !== "object" || Array.isArray(node)) return false;
  const obj = node as Record<string, unknown>;
  const [{ key, list }, ...rest] = steps;
  if (rest.length === 0) {
    if (action === "null") obj[key] = null;
    else delete obj[key];
    return true;
  }
  const child = obj[key];
  if (child === undefined || child === null) return false;
  return (list ? (child as unknown[]) : [child]).map((c) => apply(c, rest, action)).some(Boolean);
}

function documents(version: string): unknown[] {
  const docs = scenarioList.flatMap((sc) => {
    const data = read(sc.id, CONTRACTS[version].file);
    return Array.isArray(data) ? data : [data];
  });
  if (version === "case.v1") {
    // No scenario has pathology results; its items are the same type as labs (see the backend test).
    const synthetic = structuredClone(docs[0]) as { investigations: { labs: unknown[]; pathology: unknown[] } };
    synthetic.investigations.pathology = structuredClone(synthetic.investigations.labs);
    docs.push(synthetic);
  }
  return docs;
}

describe.each(Object.entries(CONTRACT_SHAPES))("%s: optional means absent, never null", (version, shape) => {
  it.each(shape.optional)("%s", (path) => {
    const { decode } = CONTRACTS[version];
    const steps = parse(path);
    let exercised = false;
    for (const doc of documents(version)) {
      decode(doc); // baseline is valid
      const withNull = structuredClone(doc);
      if (!apply(withNull, steps, "null")) continue;
      exercised = true;
      expect(() => decode(withNull), `${version}:${path} accepted an explicit null`).toThrow();
      if (!CONDITIONALLY_REQUIRED.has(`${version}:${path}`)) {
        const absent = structuredClone(doc);
        apply(absent, steps, "absent");
        expect(() => decode(absent)).not.toThrow();
      }
      break;
    }
    expect(exercised, `no fixture contains an object at ${path}`).toBe(true);
  });
});

describe("free-form content may hold nulls (z.unknown())", () => {
  it("accepts null inside `extensions`", () => {
    const doc = structuredClone(read("cardiology", "specialist_reports.v1.json") as Record<string, unknown>[])[0];
    doc.extensions = { cardiology: { score: null } };
    expect(() => decodeSpecialistReport(doc)).not.toThrow();
  });
});
