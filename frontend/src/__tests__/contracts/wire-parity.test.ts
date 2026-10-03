import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import { z, type ZodObject, type ZodRawShape } from "zod";
import { createHttpApi, createHttpClient } from "@/lib/api/http";
import { MeWireSchema } from "@/lib/api/http/me";
import {
  CaseSummaryWireSchema,
  DocumentItemWireSchema,
  SafetyCheckWireSchema,
  UploadUrlWireSchema,
  encodeNewCase,
} from "@/lib/api/http/resources";

/**
 * The frontend's wire schemas against the backend's committed API surface
 * (backend/tests/fixtures/api-surface.json, itself checked against the real OpenAPI by a backend test).
 * Add, rename or make optional a field on one side only and a test fails.
 */
interface Surface {
  paths: Record<string, string[]>;
  models: Record<string, { properties: string[]; required: string[] }>;
}
const surface = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../../backend/tests/fixtures/api-surface.json", import.meta.url)), "utf8"),
) as Surface;

function shapeOf(schema: ZodObject<ZodRawShape>) {
  const keys = Object.keys(schema.shape).sort();
  const required = keys.filter((k) => !z.safeParse(schema.shape[k], undefined).success);
  return { properties: keys, required };
}

describe("response models: property names and required-ness match the backend", () => {
  const pairs: [string, ZodObject<ZodRawShape>][] = [
    ["CaseSummary", CaseSummaryWireSchema],
    ["DocumentItem", DocumentItemWireSchema],
    ["UploadUrlResponse", UploadUrlWireSchema],
    ["MeResponse", MeWireSchema],
  ];
  for (const [name, schema] of pairs) {
    it(name, () => expect(shapeOf(schema)).toEqual(surface.models[name]));
  }

  it("SafetyCheckResult (category is optional on both sides)", () => {
    const backend = surface.models.SafetyCheckResult;
    expect(shapeOf(SafetyCheckWireSchema).properties).toEqual(backend.properties);
    expect(shapeOf(SafetyCheckWireSchema).required).toEqual(backend.required);
  });
});

describe("request bodies the frontend builds only use fields the backend defines", () => {
  it("NewCaseInput", () => {
    const full = encodeNewCase({ concern: "c", ageYears: 1, sex: "F", intent: "i", proposedTreatment: "t" });
    expect(Object.keys(full).sort()).toEqual(surface.models.NewCaseInput.properties);
    for (const required of surface.models.NewCaseInput.required) expect(full).toHaveProperty(required);
  });
});

describe("every endpoint the HTTP API calls exists on the backend", () => {
  it("method + path template", async () => {
    const seen = new Set<string>();
    vi.stubGlobal("fetch", async () => new Response(null, { status: 200 }));
    try {
      const client = createHttpClient({
        baseUrl: "http://api.test",
        fetchImpl: (async (url: string, init: RequestInit) => {
          const path = url.replace("http://api.test", "");
          seen.add(`${(init.method ?? "GET").toLowerCase()} ${path}`);
          // Enough of a valid answer for each call to complete.
          if (path.endsWith("/upload-url")) return new Response(JSON.stringify({ document_id: "d", upload_url: "https://s.test/u", expires_in: 1 }), { status: 200 });
          if (path.endsWith("/complete")) return new Response(JSON.stringify({ id: "d", name: "a.pdf", type: "other", size_kb: 1, status: "ready", uploaded_at: "2026-01-01" }), { status: 200 });
          return new Response(JSON.stringify({ error: { code: "CASE_NOT_FOUND", message: "m", request_id: "r", details: {} } }), { status: 404 });
        }) as typeof fetch,
      });
      const api = createHttpApi(client);
      const file = new File([new Uint8Array([1])], "a.pdf", { type: "application/pdf" });
      await Promise.allSettled([
        api.listCases(), api.getCase("c1"), api.createCase({ concern: "c", ageYears: 1, sex: "F" }), api.deleteCase("c1"),
        api.safetyCheck({ text: "t", currentSymptoms: [] }), api.getDocuments("c1"), api.uploadDocument("c1", { name: "a.pdf", sizeKb: 1, blob: file }),
        api.removeDocument("c1", "d1"), api.getRun("r1"),
      ]);
    } finally {
      vi.unstubAllGlobals();
    }
    const templates = Object.entries(surface.paths).flatMap(([p, methods]) =>
      methods.map((m) => ({ m, re: new RegExp(`^${p.replace(/\{[^}]+\}/g, "[^/]+")}$`) })),
    );
    expect(seen.size).toBeGreaterThanOrEqual(9);
    for (const call of seen) {
      const [method, path] = call.split(" ");
      expect(templates.some((t) => t.m === method && t.re.test(path)), call).toBe(true);
    }
  });
});
