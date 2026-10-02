import type { ExternalSource } from "@/domain/types";
import { src, type ScenarioData } from "./types";

/**
 * "Hard case" 2 — conflicting reports.
 * Arjun Mehta, 38, is entirely fictional. Two documents describe the same MRI
 * differently, and specialist perspectives genuinely differ. The UI must keep
 * both visible and never pick a winner.
 */

export const conflictingSources: ExternalSource[] = [
  {
    id: "src_neuro_7",
    title: "Sample summary: when an imaging report and a clinical summary disagree",
    publisher: "AdvisorAI sample evidence library (synthetic placeholder)",
    year: 2024,
    licence: "Prototype placeholder, not a real guideline",
    section: "§5 Discrepant reports",
    snippet:
      "When two documents describe the same scan differently, a formal re-read or clarification from the reporting radiologist is commonly requested before conclusions are drawn.",
  },
  {
    id: "src_neuro_9",
    title: "Sample summary: recurrent headaches with brief visual symptoms",
    publisher: "AdvisorAI sample evidence library (synthetic placeholder)",
    year: 2023,
    licence: "Prototype placeholder, not a real guideline",
    section: "§1 Patterns",
    snippet: "Recurrent headaches with short-lasting visual symptoms are a pattern in which migraine with aura is commonly considered. A clinician confirms the cause.",
  },
  {
    id: "src_drug_8",
    title: "Sample summary: frequent painkiller use and headaches",
    publisher: "AdvisorAI sample evidence library (synthetic placeholder)",
    year: 2023,
    licence: "Prototype placeholder, not a real drug label",
    section: "§2 Frequency",
    snippet: "Using painkillers on many days each month is associated with more frequent headaches in some people. A prescriber usually reviews this.",
  },
];

export const conflicting: ScenarioData = {
  id: "conflicting",
  seedCase: {
    id: "c_m77",
    code: "AC-M77",
    ownerLabel: "Arjun M. (fictional)",
    ageYears: 38,
    sex: "M",
    concern: "My MRI report and my discharge summary seem to say different things. What is actually being said?",
    proposedTreatment: "Follow-up MRI in 3 months and a neurology review",
    status: "complete",
    scenario: "conflicting",
    documentCount: 5,
    updatedAt: "2026-09-30T11:25:00Z",
    runId: "r_80",
    specialtyLabel: "Head and nerves",
  },
  documents: [
    { id: "d_mri", name: "MRI brain report.pdf", type: "imaging", pages: 2, sizeKb: 702, status: "ready", uploadedAt: "2026-09-27T09:00:00Z" },
    { id: "d_dis", name: "Hospital discharge summary.pdf", type: "discharge", pages: 2, sizeKb: 455, status: "ready", uploadedAt: "2026-09-27T09:01:00Z" },
    { id: "d_neu", name: "Neurology consultation note.pdf", type: "consult", pages: 2, sizeKb: 388, status: "ready", uploadedAt: "2026-09-27T09:02:00Z" },
    { id: "d_lab4", name: "Routine blood tests.pdf", type: "lab", pages: 1, sizeKb: 221, status: "ready", uploadedAt: "2026-09-27T09:03:00Z" },
    { id: "d_rx3", name: "Current medicines.jpg", type: "prescription", pages: 1, sizeKb: 840, status: "ready", ocrConfidence: 0.9, uploadedAt: "2026-09-27T09:04:00Z" },
  ],
  facts: [
    { id: "f_a1", type: "symptom", label: "Recurrent headaches with brief flashing lights", value: "Since May", date: "2026-05-10", confidence: 0.9, source: src("d_neu", 1, "History", "Recurrent headaches since May, preceded by about 20 minutes of flashing lights.") },
    { id: "f_a2", type: "imaging", label: "MRI report impression", value: "No intracranial abnormality", date: "2026-07-14", confidence: 0.95, source: src("d_mri", 2, "Impression", "No intracranial abnormality identified.") },
    { id: "f_a3", type: "imaging", label: "Discharge summary description of the MRI", value: "Small lesion, right frontal lobe", flag: "abnormal", date: "2026-07-17", confidence: 0.9, source: src("d_dis", 1, "Investigations", "MRI brain (17-Jul): small lesion in the right frontal lobe, for follow-up.") },
    { id: "f_a4", type: "recommendation", label: "Discharge plan", value: "Follow-up MRI in 3 months and neurology review", date: "2026-07-17", confidence: 0.92, source: src("d_dis", 2, "Plan", "Repeat MRI in 3 months. Neurology review.") },
    { id: "f_a5", type: "lab_result", label: "Routine blood tests", value: "Within the reference ranges", date: "2026-06-30", confidence: 0.96, source: src("d_lab4", 1, "Summary", "All parameters within reference range.") },
    { id: "f_a6", type: "diagnosis", label: "Migraine with aura (suspected)", value: "Suspected", date: "2026-06-30", confidence: 0.84, source: src("d_neu", 2, "Impression", "Features suggest migraine with aura. Imaging requested to exclude other causes.") },
    { id: "f_am1", type: "medication", label: "Sumatriptan", value: "50 mg, when needed", date: "2026-06-30", confidence: 0.9, source: src("d_rx3", 1, "Medicines", "Tab. Sumatriptan 50 mg SOS") },
    { id: "f_am2", type: "medication", label: "Ibuprofen", value: "400 mg, when needed (about 15 days a month)", date: "2026-06-30", confidence: 0.82, source: src("d_rx3", 1, "Medicines", "Tab. Ibuprofen 400 mg SOS, using ~15 days/month") },
  ],
  timeline: {
    events: [
      { id: "tl1", date: "2026-05-10", precision: "approx", title: "Headaches with flashing lights begin", detail: "Recurrent since May.", factId: "f_a1" },
      { id: "tl2", date: "2026-06-30", precision: "day", title: "Neurology consultation", detail: "Migraine with aura suspected; MRI requested.", factId: "f_a6" },
      { id: "tl3", date: "2026-07-14", precision: "day", title: "MRI brain: report says no abnormality", detail: "Impression: no intracranial abnormality.", factId: "f_a2", conflict: "The discharge summary dates the MRI 17 July and describes a small lesion. See the next event." },
      { id: "tl4", date: "2026-07-17", precision: "day", title: "Discharge summary describes a small lesion", detail: "Follow-up MRI in 3 months advised.", factId: "f_a3", conflict: "This conflicts with the MRI report above. Both are kept; neither is treated as the correct one." },
    ],
    gaps: [
      { id: "gap1", afterEventId: "tl4", text: "No note from the reporting radiologist explaining the difference between the two documents." },
    ],
    checks: [
      "Two documents describe the same MRI differently. Both are kept.",
      "The MRI has two possible dates (14 and 17 July).",
      "One possible gap: no radiologist clarification on file.",
    ],
  },
  routing: {
    selected: [
      { specialist: "general_medicine", priority: "mandatory", reason: "Always included to give a broad view." },
      { specialist: "neurology", priority: "mandatory", reason: "Recurrent headaches with visual symptoms and an MRI discrepancy." },
      { specialist: "medication_safety", priority: "mandatory", reason: "A medicine list is present." },
    ],
    notSelected: [
      { name: "Cardiology", why: "No heart-related findings." },
      { name: "Orthopedics", why: "No bone or joint findings." },
    ],
    missingForRouting: ["Radiologist clarification of the MRI"],
  },
  specialists: [
    {
      id: "sr_gm", specialist: "general_medicine", name: "General Medicine", version: "1.0", tier: 2, priority: "mandatory",
      routingReason: "Broad view of the whole case.", status: "complete",
      confidence: { overall: "low", reason: "The key investigation is described in two conflicting ways." },
      findings: [
        { id: "ga1", statement: "Routine blood tests are within the reference ranges.", kind: "patient_fact", importance: "low", factRefs: ["f_a5"] },
        { id: "ga2", statement: "The difference between the two documents may be a wording or copying difference in one of them, but this cannot be told from the documents alone.", kind: "interpretation", importance: "high", factRefs: ["f_a2", "f_a3"] },
      ],
      uncertainties: [{ id: "gau1", text: "Which document correctly describes the scan is unknown.", impact: "high", resolvableBy: "Clarification from the reporting radiologist" }],
      missing: [{ id: "gam1", item: "Radiologist clarification of the MRI", whyItMatters: "It is the only way to settle which description is accurate." }],
      contradictions: [{ id: "gac1", description: "The MRI report and the discharge summary describe the same scan differently.", between: ["f_a2", "f_a3"] }],
      considerations: [], limitations: [],
    },
    {
      id: "sr_neuro", specialist: "neurology", name: "Neurology", version: "1.0", tier: 2, priority: "mandatory",
      routingReason: "Recurrent headaches and an MRI discrepancy.", status: "complete",
      confidence: { overall: "low", reason: "The imaging picture is unresolved." },
      findings: [
        { id: "na1", statement: "The MRI report impression states no intracranial abnormality.", kind: "patient_fact", importance: "high", factRefs: ["f_a2"] },
        { id: "na2", statement: "The discharge summary describes a small lesion in the right frontal lobe on the same scan.", kind: "patient_fact", importance: "high", factRefs: ["f_a3"] },
        { id: "na3", statement: "When two documents describe a scan differently, a formal re-read by the reporting radiologist is commonly requested before conclusions are drawn.", kind: "external_evidence", importance: "high", factRefs: [], sourceIds: ["src_neuro_7"] },
        { id: "na4", statement: "Headaches preceded by short-lasting visual symptoms are a pattern in which migraine with aura is commonly considered.", kind: "external_evidence", importance: "medium", factRefs: ["f_a1"], sourceIds: ["src_neuro_9"] },
      ],
      uncertainties: [{ id: "nau1", text: "Until the discrepancy is resolved, it is not possible to say whether the scan shows anything that needs follow-up.", impact: "high" }],
      missing: [{ id: "nam1", item: "Radiologist clarification of the MRI", whyItMatters: "Settles which description is accurate." }],
      contradictions: [{ id: "nac1", description: "MRI report vs discharge summary.", between: ["f_a2", "f_a3"] }],
      considerations: [{ id: "nc1", statement: "The planned follow-up MRI in 3 months is consistent with the discharge summary's description. Whether it is still needed depends on the clarification.", kind: "interpretation", importance: "medium", factRefs: ["f_a4"] }],
      limitations: ["The MRI images were not available, only the reports."],
    },
    {
      id: "sr_ms", specialist: "medication_safety", name: "Medication Safety", version: "1.0", tier: 2, priority: "mandatory",
      routingReason: "A medicine list is present.", status: "complete",
      confidence: { overall: "moderate", reason: "Use frequency is approximate." },
      findings: [
        { id: "ma1", statement: "Ibuprofen is used on about 15 days a month, alongside sumatriptan when needed.", kind: "patient_fact", importance: "medium", factRefs: ["f_am1", "f_am2"] },
        { id: "ma2", statement: "Using painkillers on many days each month is associated with more frequent headaches in some people. This is worth reviewing with the prescriber.", kind: "external_evidence", importance: "medium", factRefs: ["f_am2"], sourceIds: ["src_drug_8"] },
      ],
      uncertainties: [], missing: [], contradictions: [], considerations: [], limitations: [],
    },
  ],
  matrix: [
    {
      id: "mxa1", topic: "The MRI shows a lesion", relationship: "disagreement",
      cells: { general_medicine: "differs", neurology: "needs_context", medication_safety: "not_assessed" },
      summary: "The records themselves disagree. General Medicine leans toward a documentation difference; Neurology wants the radiologist to clarify. Neither view is treated as correct.",
      perspectives: [
        { specialist: "general_medicine", reasoning: "May be a wording difference in one document; cannot be told from the papers." },
        { specialist: "neurology", reasoning: "Should not be assumed either way. A formal clarification is the usual step." },
      ],
      itemIds: ["gac1", "na1", "na2", "cl_a1"],
    },
    {
      id: "mxa2", topic: "The headache pattern fits migraine with aura", relationship: "partial",
      cells: { general_medicine: "supports", neurology: "needs_context", medication_safety: "not_assessed" },
      summary: "It is a commonly considered pattern. Neurology notes this is harder to settle while the imaging question is open.",
      perspectives: [
        { specialist: "general_medicine", reasoning: "Pattern and normal bloods are consistent with it." },
        { specialist: "neurology", reasoning: "A reasonable working view, held with caution until the scan is clarified." },
      ],
      itemIds: ["na4", "cl_a4"],
    },
    {
      id: "mxa3", topic: "A follow-up MRI in 3 months is appropriate", relationship: "partial",
      cells: { general_medicine: "needs_context", neurology: "supports", medication_safety: "not_assessed" },
      summary: "Neurology supports it; General Medicine says it depends on the radiologist's clarification.",
      perspectives: [
        { specialist: "neurology", reasoning: "Consistent with the discharge description." },
        { specialist: "general_medicine", reasoning: "May not be needed if the report is confirmed as normal." },
      ],
      itemIds: ["nc1", "f_a4"],
    },
    {
      id: "mxa4", topic: "Frequent painkiller use is relevant to the headaches", relationship: "additional_context",
      cells: { general_medicine: "not_assessed", neurology: "not_assessed", medication_safety: "flags_issue" },
      summary: "Raised by Medication Safety only.",
      perspectives: [{ specialist: "medication_safety", reasoning: "Use on about half the days in a month is worth reviewing." }],
      itemIds: ["ma2", "cl_a5"],
    },
  ],
  claims: [
    { id: "cl_a1", text: "The MRI shows a small lesion in the right frontal lobe.", kind: "patient_fact", agent: "neurology", status: "contradicted", rationale: "The discharge summary says so, but the MRI report's own impression states no abnormality. Both are shown.", patientFactIds: ["f_a2", "f_a3"], externalSourceIds: [] },
    { id: "cl_a2", text: "The MRI report impression states no intracranial abnormality.", kind: "patient_fact", agent: "neurology", status: "supported", rationale: "The wording matches page 2 of the MRI report.", patientFactIds: ["f_a2"], externalSourceIds: [] },
    { id: "cl_a3", text: "When documents disagree, a radiologist re-read is commonly requested.", kind: "external_evidence", agent: "neurology", status: "supported", rationale: "Described in the reference summary.", patientFactIds: ["f_a2", "f_a3"], externalSourceIds: ["src_neuro_7"] },
    { id: "cl_a4", text: "The headache pattern is consistent with migraine with aura.", kind: "interpretation", agent: "general_medicine", status: "partially_supported", rationale: "The pattern is commonly considered, but the imaging question is open.", patientFactIds: ["f_a1", "f_a6"], externalSourceIds: ["src_neuro_9"] },
    { id: "cl_a5", text: "Frequent painkiller use is associated with more frequent headaches in some people.", kind: "external_evidence", agent: "medication_safety", status: "supported", rationale: "Use on about 15 days a month is documented; the reference describes the association.", patientFactIds: ["f_am2"], externalSourceIds: ["src_drug_8"] },
  ],
  sources: conflictingSources,
  synthesis: {
    id: "syn_run_80",
    reviewer: { label: "Interim Clinical Reviewer (AI)", tier: 3, escalated: true, escalationReason: "Two unresolved high-impact conflicts, so one reviewer step was re-run on a stronger model." },
    rubric: [
      { factor: "Patient-specific evidence present", weight: "High" },
      { factor: "Verification status of the claim", weight: "High" },
      { factor: "Source reliability and recency", weight: "Medium" },
      { factor: "Consistency with the timeline", weight: "Medium" },
      { factor: "Quality of specialist reasoning", weight: "Medium" },
      { factor: "Number of perspectives agreeing", weight: "Tie-break only" },
    ],
    items: [
      { id: "syn_1", group: "fact", kind: "patient_fact", confidence: "high", text: "You are 38 and have had recurrent headaches since May, often preceded by about 20 minutes of flashing lights. You are asking what your MRI report and discharge summary are actually saying.", derivedFrom: ["f_a1"] },
      { id: "syn_2", group: "fact", kind: "patient_fact", confidence: "high", text: "Your MRI report's conclusion says: no abnormality was identified inside the skull.", derivedFrom: ["f_a2", "cl_a2"] },
      { id: "syn_3", group: "fact", kind: "patient_fact", confidence: "high", text: "Your hospital discharge summary describes the MRI differently: a small lesion in the right frontal lobe, for follow-up.", derivedFrom: ["f_a3", "na2"] },
      { id: "syn_4", group: "fact", kind: "patient_fact", confidence: "high", text: "Your routine blood tests were within the reference ranges.", derivedFrom: ["f_a5", "ga1"] },
      { id: "syn_5", group: "fact", kind: "patient_fact", confidence: "moderate", flag: "uncertain", text: "Your neurologist documented migraine with aura as suspected, not as a confirmed diagnosis.", derivedFrom: ["f_a6", "cl_a4"] },
      { id: "syn_6", group: "fact", kind: "patient_fact", confidence: "moderate", text: "Your current medicines are sumatriptan when needed, and ibuprofen when needed (about 15 days a month).", derivedFrom: ["f_am1", "f_am2", "ma1"] },
      { id: "syn_7", group: "proposal", kind: "patient_fact", confidence: "high", text: "The discharge summary advises a repeat MRI in 3 months and a neurology review.", derivedFrom: ["f_a4", "nc1"] },
      { id: "syn_8", group: "disagreement", kind: "interpretation", confidence: "low", flag: "disagreement", impact: "high", text: "Your two documents disagree about the same scan, and the specialist perspectives differ on how to read that. One view is that it may be a wording difference in one document. Another is that it should not be assumed either way. We keep both and do not pick one.", derivedFrom: ["mxa1", "cl_a1", "tl3", "tl4"] },
      { id: "syn_9", group: "interpretation", kind: "external_evidence", confidence: "high", text: "When two documents describe the same scan differently, a formal re-read or clarification from the reporting radiologist is commonly requested before conclusions are drawn.", derivedFrom: ["cl_a3", "na3"] },
      { id: "syn_10", group: "uncertainty", kind: "interpretation", confidence: "low", flag: "uncertain", impact: "high", text: "Until the difference is clarified, it is not possible to say whether your scan shows anything that needs follow-up.", derivedFrom: ["nau1", "gau1"] },
      { id: "syn_11", group: "uncertainty", kind: "interpretation", confidence: "low", flag: "uncertain", impact: "medium", text: "Whether your headaches are migraine with aura is a working view only. It is held with caution while the imaging question is open.", derivedFrom: ["mxa2", "na4"] },
      { id: "syn_12", group: "missing", kind: "interpretation", confidence: "high", flag: "missing", impact: "high", text: "There is no note from the reporting radiologist explaining the difference between the MRI report and the discharge summary.", derivedFrom: ["nam1", "gam1"] },
      { id: "syn_13", group: "agreement", kind: "interpretation", confidence: "high", text: "The perspectives agree that the two documents cannot both be accepted as written, and that clarifying them is the key step.", derivedFrom: ["mxa1"] },
      { id: "syn_14", group: "medication", kind: "external_evidence", confidence: "moderate", impact: "medium", text: "Using painkillers on many days each month is associated with more frequent headaches in some people. You use ibuprofen on about 15 days a month. This is worth reviewing with your prescriber. Please do not change any medicine on your own.", derivedFrom: ["ma2", "cl_a5", "mxa4"] },
      { id: "syn_15", group: "clarification", kind: "interpretation", confidence: "moderate", impact: "medium", text: "Whether the repeat MRI in 3 months is still needed may depend on the radiologist's clarification.", derivedFrom: ["mxa3", "nc1"] },
      { id: "syn_16", group: "clarification", kind: "interpretation", confidence: "moderate", impact: "high", text: "Before deciding anything, it may help to get the radiologist's clarification and ask your doctors how they read the difference.", derivedFrom: ["syn_8", "syn_12"] },
    ],
  },
  reportPlan: {
    s1: ["syn_1"],
    s2: ["syn_2", "syn_3", "syn_4"],
    s4: ["syn_5"],
    s6: ["syn_6"],
    s7: ["syn_7"],
    s8: ["syn_9"],
    s9: ["syn_10", "syn_11"],
    s10: ["syn_12"],
    s11: ["syn_8", "syn_14", "syn_15"],
    s13: ["syn_13"],
    s17: ["syn_16"],
  },
  questions: [
    { id: "q1", audience: "current_doctor", priority: 1, category: "Testing", text: "My MRI report says no abnormality, but my discharge summary describes a small lesion. Can you ask the radiologist to clarify which is correct?", trigger: "Two documents describe the same scan differently.", linkedItemIds: ["syn_8", "mxa1"], status: "not_asked" },
    { id: "q2", audience: "current_doctor", priority: 1, category: "Timing", text: "Is the repeat MRI in 3 months still needed if the radiologist confirms the original report?", trigger: "The follow-up plan is based on the discharge description.", linkedItemIds: ["syn_15", "mxa3"], status: "not_asked" },
    { id: "q3", audience: "current_doctor", priority: 2, category: "Diagnosis", text: "How confident are you that my headaches are migraine with aura, given that the imaging question is open?", trigger: "The diagnosis is documented as suspected only.", linkedItemIds: ["syn_11", "syn_5"], status: "not_asked" },
    { id: "q4", audience: "current_doctor", priority: 3, category: "Medicines", text: "I use ibuprofen on about 15 days a month. Could that be affecting my headaches?", trigger: "Medication Safety flagged frequent painkiller use.", linkedItemIds: ["syn_14", "ma2"], status: "not_asked" },
    { id: "q5", audience: "second_opinion_doctor", priority: 1, category: "Testing", text: "Having seen the images, what do you see, and does it match the report or the discharge summary?", trigger: "An independent reading helps with the main conflict.", linkedItemIds: ["syn_8", "syn_12"], status: "not_asked" },
    { id: "q6", audience: "second_opinion_doctor", priority: 2, category: "Next steps", text: "Which signs would make you want a faster follow-up scan?", trigger: "Helps you plan around the uncertainty.", linkedItemIds: ["syn_10"], status: "not_asked" },
  ],
  secondOpinionDocName: "Second-opinion neurology note (synthetic).pdf",
  secondOpinionFacts: [
    { id: "so_a1", type: "recommendation", label: "Second opinion: request a formal radiology re-read", date: "2026-09-26", confidence: 0.9, source: src("d_so", 1, "Plan", "Request formal re-read of the MRI by the reporting radiologist.") },
    { id: "so_a2", type: "recommendation", label: "Second opinion: lesion not confirmed on review of the report", date: "2026-09-26", confidence: 0.86, source: src("d_so", 1, "Assessment", "A lesion is not confirmed on the written report. Awaiting re-read.") },
    { id: "so_a3", type: "recommendation", label: "Second opinion: headache diary", date: "2026-09-26", confidence: 0.9, source: src("d_so", 2, "Plan", "Keep a headache diary including painkiller days.") },
  ],
  comparison: {
    opinionALabel: "Your treating team (discharge summary)",
    opinionBLabel: "Second-opinion doctor",
    rows: [
      { id: "cmp1", topic: "What the MRI shows", opinionA: "A small lesion in the right frontal lobe, for follow-up.", opinionB: "A lesion is not confirmed on the written report; awaiting a formal re-read.", evidenceA: ["f_a3"], evidenceB: ["f_a2", "so_a2"], relationship: "differs", itemIds: ["syn_8", "so_a2"] },
      { id: "cmp2", topic: "Radiology re-read", opinionA: "Not mentioned.", opinionB: "Requests a formal re-read.", evidenceA: [], evidenceB: ["so_a1"], relationship: "new_info", itemIds: ["syn_12", "so_a1"] },
      { id: "cmp3", topic: "Follow-up MRI in 3 months", opinionA: "Advised.", opinionB: "Depends on the re-read.", evidenceA: ["f_a4"], evidenceB: ["so_a1"], relationship: "unresolved", itemIds: ["syn_15", "so_a1"] },
      { id: "cmp4", topic: "Painkiller days", opinionA: "Not discussed.", opinionB: "Suggests a diary that includes painkiller days.", evidenceA: [], evidenceB: ["so_a3"], relationship: "changed", itemIds: ["syn_14", "so_a3"] },
    ],
    nextQuestions: [
      { audience: "Your current doctor", text: "Your second-opinion doctor has asked for a formal radiology re-read. Can that be arranged?", itemIds: ["cmp2"] },
      { audience: "Both doctors", text: "If the re-read matches the original report, is the 3-month MRI still needed?", itemIds: ["cmp3"] },
    ],
    answeredByOpinion: [{ questionId: "q1", note: "The second opinion also asks for a formal re-read.", status: "partially_answered" }],
  },
  highlights: [
    { id: "syn_8", text: "Your MRI report and your discharge summary describe the same scan differently.", flag: "disagreement" },
    { id: "syn_12", text: "No radiologist note explains the difference.", flag: "missing" },
    { id: "syn_10", text: "It is not possible to say yet whether the scan needs follow-up.", flag: "uncertain" },
    { id: "syn_7", text: "A repeat MRI in 3 months has been advised." },
  ],
  runWarnings: [],
  stepNotes: { 10: "Two documents conflict. Both are kept." },
  finalStatus: "complete",
};
