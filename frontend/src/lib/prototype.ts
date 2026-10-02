import { prototypeControls } from "@/mocks/mock-api";
import type { PrototypeControls } from "./prototype-types";
import { invalidateQueries } from "./use-query";

export type { PrototypeControls, SampleCase } from "./prototype-types";

/**
 * Prototype-only controls, or `null` when a real backend is configured.
 * Screens use `prototype?.…` so these affordances disappear automatically in
 * production without any screen changes.
 */
export const prototype: PrototypeControls | null =
  process.env.NEXT_PUBLIC_API_MODE === "http"
    ? null
    : {
        ...prototypeControls,
        async attachSampleRecords(caseId, scenario) {
          const result = await prototypeControls.attachSampleRecords(caseId, scenario);
          invalidateQueries();
          return result;
        },
        async skipToResults(runId) {
          await prototypeControls.skipToResults(runId);
          invalidateQueries();
        },
      };
