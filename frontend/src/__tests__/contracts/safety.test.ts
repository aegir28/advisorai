import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { mockApi } from "@/mocks/mock-api";

/**
 * The red-flag rules exist twice: here (the prototype mock) and in backend/app/safety/red_flags.py. Both are run
 * against the SAME fixture, so a change to one that is not made to the other fails a test.
 */
interface Case { name: string; text: string; currentSymptoms: string[]; redFlag: boolean; matched: string[]; category: string | null }
const fixture = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../../backend/tests/fixtures/safety_cases.json", import.meta.url)), "utf8"),
) as { cases: Case[] };

describe("safety gate parity with the backend", () => {
  for (const c of fixture.cases) {
    it(c.name, async () => {
      const r = await mockApi.safetyCheck({ text: c.text, currentSymptoms: c.currentSymptoms });
      expect(r.redFlag).toBe(c.redFlag);
      expect(r.matched).toEqual(c.matched);
      expect(r.category ?? null).toBe(c.category);
    });
  }
});
