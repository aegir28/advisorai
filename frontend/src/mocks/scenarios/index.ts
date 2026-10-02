import type { ScenarioId, SpecialistId } from "@/domain/types";
import { cardiology } from "./cardiology";
import { conflicting } from "./conflicting";
import { missingInfo } from "./missing-info";
import type { ScenarioData } from "./types";

export const scenarios: Record<ScenarioId, ScenarioData> = {
  cardiology,
  missing_info: missingInfo,
  conflicting,
};

export const scenarioList: ScenarioData[] = [cardiology, missingInfo, conflicting];

/** Scenario backing each seeded case. */
export const seededCaseIds: Record<string, ScenarioId> = {
  c_9f2: "cardiology",
  c_k21: "missing_info",
  c_m77: "conflicting",
};

/** What each hard-case scenario is meant to demonstrate. */
export const scenarioBlurbs: Record<ScenarioId, { title: string; blurb: string }> = {
  cardiology: {
    title: "Heart and diabetes",
    blurb: "A full, well-documented case. Angioplasty is proposed, and perspectives differ on timing.",
  },
  missing_info: {
    title: "Missing information",
    blurb: "Knee surgery is suggested, but the MRI report is missing, one file is unreadable and one perspective did not finish.",
  },
  conflicting: {
    title: "Conflicting reports",
    blurb: "An MRI report and a discharge summary describe the same scan differently. Both views stay visible.",
  },
};

export const specialistNames: Record<SpecialistId, string> = {
  general_medicine: "General Medicine",
  cardiology: "Cardiology",
  interventional_cardiology: "Interventional Cardiology",
  medication_safety: "Medication Safety",
  orthopedics: "Orthopedics",
  neurology: "Neurology",
};
