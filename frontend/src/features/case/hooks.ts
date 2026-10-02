"use client";

import { api } from "@/lib/api";
import { useQuery } from "@/lib/use-query";

/**
 * Feature-level data hooks. Screens only ever call these; they never import
 * the mock directly. Swapping the backend therefore needs no screen changes.
 */

export const useCases = () => useQuery("cases", () => api.listCases());
export const useCase = (id: string) => useQuery(`case:${id}`, () => api.getCase(id));
export const useCaseOverview = (id: string) => useQuery(`overview:${id}`, () => api.getCaseOverview(id));
export const useDocuments = (id: string) => useQuery(`docs:${id}`, () => api.getDocuments(id));
export const useTimeline = (id: string) => useQuery(`timeline:${id}`, () => api.getTimeline(id));
export const usePerspectives = (id: string) => useQuery(`persp:${id}`, () => api.getPerspectives(id));
export const useEvidence = (id: string) => useQuery(`evidence:${id}`, () => api.getEvidence(id));
export const useCrossReview = (id: string) => useQuery(`review:${id}`, () => api.getCrossReview(id));
export const useSynthesis = (id: string) => useQuery(`synthesis:${id}`, () => api.getSynthesis(id));
export const useReport = (id: string) => useQuery(`report:${id}`, () => api.getReport(id));
export const useQuestions = (id: string) => useQuery(`questions:${id}`, () => api.getQuestions(id));
export const useComparison = (id: string) => useQuery(`comparison:${id}`, () => api.getComparison(id));

export const useRun = (runId: string | undefined) =>
  useQuery(
    `run:${runId ?? "none"}`,
    () => (runId ? api.getRun(runId) : Promise.resolve(null)),
    {
      enabled: !!runId,
      refetchInterval: (run) => (run && run.status === "running" ? 700 : false),
    },
  );

export const useSecondOpinion = (id: string) =>
  useQuery(`so:${id}`, () => api.getSecondOpinion(id), {
    refetchInterval: (s) => (s && s.status === "processing" ? 900 : false),
  });

export const useTrace = (caseId: string, itemId: string | null) =>
  useQuery(`trace:${caseId}:${itemId ?? "none"}`, () => (itemId ? api.getTrace(caseId, itemId) : Promise.resolve(null)), {
    enabled: !!itemId,
  });
