/**
 * Single source of truth for the product identity.
 * Change the name here and it propagates to the UI, metadata and copy.
 */
export const BRAND = {
  name: "AdvisorAI",
  tagline: "Before you take a second opinion, know exactly what to ask.",
  description:
    "Decision-support and second-opinion preparation. AdvisorAI helps you understand your medical records and prepare questions for a qualified doctor.",
  /** The prototype runs on fictional data only. */
  isPrototype: true,
} as const;

export const EMERGENCY_NUMBERS = ["112", "108"] as const;
