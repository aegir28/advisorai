import type { ExternalSource } from "@/domain/types";
import { src, type ScenarioData } from "./types";

/**
 * "Hard case" 1 — missing information.
 * Meera Iyer, 47, is entirely fictional. The case is built to show how the UI
 * handles unreadable documents, uncertain values, an incomplete specialist
 * perspective and a key report that simply is not there.
 */

export const missingInfoSources: ExternalSource[] = [
  {
    id: "src_ortho_5",
    title: "Sample summary: arthroscopy for meniscus symptoms",
    publisher: "AdvisorAI sample evidence library (synthetic placeholder)",
    year: 2024,
    licence: "Prototype placeholder, not a real guideline",
    section: "§2 When surgery is discussed",
    snippet:
      "Keyhole surgery is commonly discussed when a confirmed tear causes locking or catching, usually after a period of non-surgical care. It is generally less helpful for pain caused mainly by wear-related changes.",
  },
  {
    id: "src_ortho_6",
    title: "Sample summary: role of imaging before knee surgery",
    publisher: "AdvisorAI sample evidence library (synthetic placeholder)",
    year: 2023,
    licence: "Prototype placeholder, not a real guideline",
    section: "§1 Imaging",
    snippet: "MRI is commonly used to confirm a suspected meniscus tear and to look for other causes of pain before surgery is planned.",
  },
];

export const missingInfo: ScenarioData = {
  id: "missing_info",
  seedCase: {
    id: "c_k21",
    code: "AC-K21",
    ownerLabel: "Meera I. (fictional)",
    ageYears: 47,
    sex: "F",
    concern: "Do I really need knee surgery, or is there something missing from my records?",
    proposedTreatment: "Arthroscopic partial meniscectomy (right knee)",
    status: "partial",
    scenario: "missing_info",
    documentCount: 5,
    updatedAt: "2026-10-01T16:40:00Z",
    runId: "r_78",
    title: "Knee pain",
    specialtyLabel: "Knee and bones",
  },
  documents: [
    { id: "d_oc", name: "Orthopaedic consultation note.pdf", type: "consult", pages: 2, sizeKb: 498, status: "ready", uploadedAt: "2026-09-29T08:00:00Z" },
    { id: "d_xr", name: "Right knee X-ray report.pdf", type: "imaging", pages: 1, sizeKb: 640, status: "needs_attention", ocrConfidence: 0.58, note: "Scan quality is low. One measurement could not be read with confidence and is marked uncertain.", uploadedAt: "2026-09-29T08:01:00Z" },
    { id: "d_mri", name: "MRI films photo.jpg", type: "imaging", pages: 1, sizeKb: 2890, status: "needs_attention", ocrConfidence: 0.12, note: "We couldn't read this image. A clear copy of the written MRI report would help.", uploadedAt: "2026-09-29T08:02:00Z" },
    { id: "d_rx2", name: "Current medicines.jpg", type: "prescription", pages: 1, sizeKb: 910, status: "ready", ocrConfidence: 0.88, uploadedAt: "2026-09-29T08:03:00Z" },
    { id: "d_dup", name: "Right knee X-ray report (copy).pdf", type: "imaging", pages: 1, sizeKb: 640, status: "duplicate", note: "Identical to a file you already added, so it was skipped. No extra cost.", uploadedAt: "2026-09-29T08:04:00Z" },
  ],
  facts: [
    { id: "f_k1", type: "symptom", label: "Right knee pain with twisting", value: "Since March", date: "2026-03-10", confidence: 0.9, source: src("d_oc", 1, "History", "Right knee pain on twisting for about three months, occasional catching.") },
    { id: "f_k2", type: "symptom", label: "Occasional catching sensation", value: "Not described as locking", date: "2026-06-18", confidence: 0.86, source: src("d_oc", 1, "History", "Occasional catching. No true locking reported.") },
    { id: "f_k3", type: "treatment_history", label: "Physiotherapy", value: "2 sessions only", date: "2026-04-14", confidence: 0.88, source: src("d_oc", 2, "Treatment so far", "Physiotherapy: 2 sessions in April, stopped due to schedule.") },
    { id: "f_xr1", type: "imaging", label: "X-ray: medial joint space narrowing", value: "Mild (value unclear)", flag: "abnormal", date: "2026-05-22", confidence: 0.58, uncertainValue: true, source: src("d_xr", 1, "Findings", "Mild narrowing of the medial joint space, approx. 3.? mm (unclear in scan).") },
    { id: "f_k4", type: "diagnosis", label: "Medial meniscus tear (suspected)", value: "Suspected, not confirmed", date: "2026-06-18", confidence: 0.82, source: src("d_oc", 2, "Impression", "Likely medial meniscus tear. MRI reviewed in clinic.") },
    { id: "f_k5", type: "recommendation", label: "Surgeon's suggestion", value: "Arthroscopic partial meniscectomy", date: "2026-06-18", confidence: 0.9, source: src("d_oc", 2, "Plan", "Advise arthroscopic partial meniscectomy, right knee.") },
    { id: "f_km1", type: "medication", label: "Ibuprofen", value: "400 mg, three times a day", date: "2026-06-18", confidence: 0.86, source: src("d_rx2", 1, "Medicines", "Tab. Ibuprofen 400 mg TDS x 3 months") },
    { id: "f_km2", type: "medication", label: "Pantoprazole", value: "40 mg, once daily", date: "2026-06-18", confidence: 0.88, source: src("d_rx2", 1, "Medicines", "Tab. Pantoprazole 40 mg OD") },
  ],
  timeline: {
    events: [
      { id: "tl1", date: "2026-03-10", precision: "approx", title: "Knee pain begins", detail: "Pain on twisting, occasional catching.", factId: "f_k1" },
      { id: "tl2", date: "2026-04-14", precision: "day", title: "Physiotherapy: two sessions", detail: "Stopped after two sessions.", factId: "f_k3" },
      { id: "tl3", date: "2026-05-22", precision: "day", title: "X-ray of the right knee", detail: "Mild medial narrowing, one value unclear.", factId: "f_xr1", conflict: "The scan reads 22 May in one place and 2 May in another. Both are kept; please check the original." },
      { id: "tl4", date: "2026-06-18", precision: "day", title: "Orthopaedic consultation", detail: "Keyhole surgery suggested.", factId: "f_k5" },
    ],
    gaps: [
      { id: "gap1", afterEventId: "tl3", text: "The consultation mentions an MRI, but no MRI report is on file." },
    ],
    checks: [
      "One event has two possible dates and is flagged.",
      "One possible gap found: no written MRI report.",
      "One value is marked uncertain rather than guessed.",
    ],
  },
  routing: {
    selected: [
      { specialist: "general_medicine", priority: "mandatory", reason: "Always included to give a broad view." },
      { specialist: "orthopedics", priority: "mandatory", reason: "Knee imaging and a surgical suggestion are documented." },
      { specialist: "medication_safety", priority: "mandatory", reason: "A medicine list is present." },
    ],
    notSelected: [
      { name: "Cardiology", why: "No heart-related findings." },
      { name: "Neurology", why: "No neurological findings." },
    ],
    missingForRouting: ["Written MRI report", "Weight-bearing X-ray views"],
  },
  specialists: [
    {
      id: "sr_gm", specialist: "general_medicine", name: "General Medicine", version: "1.0", tier: 2, priority: "mandatory",
      routingReason: "Broad view of the whole case.", status: "complete",
      confidence: { overall: "low", reason: "Key documents are missing or hard to read." },
      findings: [
        { id: "gk1", statement: "Only two physiotherapy sessions are recorded before surgery was suggested.", kind: "patient_fact", importance: "high", factRefs: ["f_k3"] },
        { id: "gk2", statement: "Ibuprofen 400 mg three times a day for about three months is listed.", kind: "patient_fact", importance: "medium", factRefs: ["f_km1"] },
      ],
      uncertainties: [{ id: "gku1", text: "How much non-surgical care has been tried is not clear from the records.", impact: "high", resolvableBy: "Treating doctor or physiotherapist notes" }],
      missing: [{ id: "gkm1", item: "Details of non-surgical treatment so far", whyItMatters: "Surgery is usually discussed after a period of non-surgical care." }],
      contradictions: [], considerations: [], limitations: ["Two documents could not be read fully."],
    },
    {
      id: "sr_ortho", specialist: "orthopedics", name: "Orthopedics", version: "1.1", tier: 2, priority: "mandatory",
      routingReason: "Knee imaging and a surgical suggestion are documented.", status: "complete",
      confidence: { overall: "low", reason: "The MRI report is not available and one X-ray value is uncertain." },
      findings: [
        { id: "ok1", statement: "Pain on twisting with occasional catching is described since March.", kind: "patient_fact", importance: "high", factRefs: ["f_k1", "f_k2"] },
        { id: "ok2", statement: "The consultation suggests a meniscus tear, but this cannot be confirmed here because the MRI report is missing.", kind: "interpretation", importance: "high", factRefs: ["f_k4"] },
        { id: "ok3", statement: "Keyhole surgery is commonly discussed for a confirmed tear with catching or locking, usually after non-surgical care.", kind: "external_evidence", importance: "medium", factRefs: [], sourceIds: ["src_ortho_5"] },
      ],
      uncertainties: [
        { id: "oku1", text: "An X-ray measurement could not be read reliably, so the degree of joint narrowing is uncertain.", impact: "medium" },
        { id: "oku2", text: "Whether the pain comes mainly from a tear or from wear-related changes is not clear from the records.", impact: "high" },
      ],
      missing: [
        { id: "okm1", item: "Written MRI report", whyItMatters: "Commonly used to confirm a suspected tear before surgery." },
        { id: "okm2", item: "Weight-bearing X-ray views", whyItMatters: "Help judge joint wear more reliably." },
      ],
      contradictions: [], considerations: [], limitations: ["Only the written reports were reviewed, not the images."],
    },
    {
      id: "sr_ms", specialist: "medication_safety", name: "Medication Safety", version: "1.0", tier: 2, priority: "mandatory",
      routingReason: "A medicine list is present.", status: "incomplete",
      statusNote: "This perspective could not be completed. The report continues without it and says so.",
      confidence: { overall: "low", reason: "The review did not finish." },
      findings: [],
      uncertainties: [], missing: [], contradictions: [], considerations: [],
      limitations: ["Incomplete: the structured response did not pass validation after one repair attempt."],
    },
  ],
  matrix: [
    {
      id: "mxk1", topic: "A meniscus tear has been confirmed", relationship: "missing_info",
      cells: { general_medicine: "flags_issue", orthopedics: "flags_issue", medication_safety: "not_assessed" },
      summary: "Both perspectives note that the document that would confirm this (the MRI report) is missing.",
      perspectives: [
        { specialist: "general_medicine", reasoning: "The records suggest a tear but do not contain the report that would confirm it." },
        { specialist: "orthopedics", reasoning: "The consultation says the MRI was reviewed in clinic, but there is no written report." },
      ],
      itemIds: ["okm1", "ok2"],
    },
    {
      id: "mxk2", topic: "Non-surgical care has been tried for long enough", relationship: "missing_info",
      cells: { general_medicine: "flags_issue", orthopedics: "needs_context", medication_safety: "not_assessed" },
      summary: "Only two physiotherapy sessions are recorded. Whether other approaches were tried is not documented.",
      perspectives: [
        { specialist: "general_medicine", reasoning: "Two sessions is a short trial." },
        { specialist: "orthopedics", reasoning: "May have been discussed in clinic; not written down." },
      ],
      itemIds: ["gk1", "gkm1"],
    },
    {
      id: "mxk3", topic: "Regular ibuprofen use is relevant", relationship: "additional_context",
      cells: { general_medicine: "flags_issue", orthopedics: "not_assessed", medication_safety: "not_assessed" },
      summary: "Raised by General Medicine. The Medication Safety perspective could not complete, so this was not cross-checked.",
      perspectives: [{ specialist: "general_medicine", reasoning: "Three months of regular ibuprofen is worth reviewing with the prescriber." }],
      itemIds: ["gk2"],
    },
  ],
  claims: [
    { id: "clk1", text: "Ibuprofen 400 mg three times a day is on the current medicine list.", kind: "patient_fact", agent: "general_medicine", status: "supported", rationale: "The value matches the prescription image.", patientFactIds: ["f_km1"], externalSourceIds: [] },
    { id: "clk2", text: "Keyhole surgery is commonly discussed for a confirmed tear with catching, after non-surgical care.", kind: "external_evidence", agent: "orthopedics", status: "partially_supported", rationale: "The reference supports the general statement; the tear is not confirmed and non-surgical care is poorly documented.", patientFactIds: ["f_k1", "f_k2", "f_k3"], externalSourceIds: ["src_ortho_5"] },
    { id: "clk3", text: "A meniscus tear is present.", kind: "interpretation", agent: "orthopedics", status: "insufficient_evidence", rationale: "The MRI report that would confirm this is not in the records.", patientFactIds: ["f_k4"], externalSourceIds: ["src_ortho_6"] },
    { id: "clk4", text: "The X-ray shows medial joint space narrowing.", kind: "patient_fact", agent: "orthopedics", status: "unclear", rationale: "The scan quality is low and the measurement is marked uncertain.", patientFactIds: ["f_xr1"], externalSourceIds: [] },
  ],
  sources: missingInfoSources,
  synthesis: {
    id: "syn_run_78",
    reviewer: { label: "Interim Clinical Reviewer (AI)", tier: 3, escalated: true, escalationReason: "High uncertainty: key documents are missing, so one reviewer step was re-run on a stronger model." },
    rubric: [
      { factor: "Patient-specific evidence present", weight: "High" },
      { factor: "Verification status of the claim", weight: "High" },
      { factor: "Source reliability and recency", weight: "Medium" },
      { factor: "Consistency with the timeline", weight: "Medium" },
      { factor: "Quality of specialist reasoning", weight: "Medium" },
      { factor: "Number of perspectives agreeing", weight: "Tie-break only" },
    ],
    items: [
      { id: "syn_1", group: "fact", kind: "patient_fact", confidence: "high", text: "You are 47 and have had right knee pain with twisting since March, with an occasional catching feeling. You are asking whether surgery is really needed.", derivedFrom: ["f_k1", "f_k2"] },
      { id: "syn_2", group: "fact", kind: "patient_fact", confidence: "low", flag: "uncertain", text: "Your X-ray report mentions mild narrowing on the inner side of the knee. One measurement in the scan was hard to read, so we haven't guessed it.", derivedFrom: ["f_xr1", "clk4"] },
      { id: "syn_3", group: "fact", kind: "patient_fact", confidence: "high", text: "Your orthopaedic consultation suggests a torn cartilage pad (medial meniscus) and advises keyhole surgery.", derivedFrom: ["f_k4", "f_k5"] },
      { id: "syn_4", group: "fact", kind: "patient_fact", confidence: "moderate", flag: "uncertain", text: "A medial meniscus tear is documented as suspected. It is not confirmed by a written report in your records.", derivedFrom: ["f_k4", "clk3"] },
      { id: "syn_5", group: "fact", kind: "patient_fact", confidence: "high", text: "Your medicine list shows ibuprofen 400 mg three times a day, and pantoprazole once a day.", derivedFrom: ["f_km1", "f_km2", "clk1"] },
      { id: "syn_6", group: "proposal", kind: "patient_fact", confidence: "high", text: "Your surgeon advised arthroscopic partial meniscectomy (keyhole surgery on the cartilage) of the right knee.", derivedFrom: ["f_k5"] },
      { id: "syn_7", group: "interpretation", kind: "external_evidence", confidence: "low", flag: "uncertain", text: "General reference material says keyhole surgery is commonly discussed for a confirmed tear with catching, usually after a period of non-surgical care. Neither of those is fully documented in your records.", derivedFrom: ["clk2", "ok3"] },
      { id: "syn_8", group: "uncertainty", kind: "interpretation", confidence: "low", flag: "uncertain", impact: "high", text: "It is not clear whether your pain comes mainly from a tear or from wear-related changes in the joint.", derivedFrom: ["oku2", "oku1"] },
      { id: "syn_9", group: "uncertainty", kind: "interpretation", confidence: "low", flag: "uncertain", impact: "medium", text: "How much non-surgical care has been tried is not clear. Only two physiotherapy sessions are recorded.", derivedFrom: ["gku1", "gk1"] },
      { id: "syn_10", group: "missing", kind: "interpretation", confidence: "high", flag: "missing", impact: "high", text: "Your records do not include a written MRI report. The consultation mentions an MRI, but only a photo of films was uploaded and it could not be read. A clear copy of the report would help.", derivedFrom: ["mxk1", "okm1"] },
      { id: "syn_11", group: "missing", kind: "interpretation", confidence: "moderate", flag: "missing", impact: "medium", text: "Details of any non-surgical treatment (such as a longer physiotherapy trial) are not in your records.", derivedFrom: ["mxk2", "gkm1"] },
      { id: "syn_12", group: "missing", kind: "interpretation", confidence: "moderate", flag: "missing", impact: "low", text: "Weight-bearing X-ray views are not in your records. They help judge joint wear more reliably.", derivedFrom: ["okm2"] },
      { id: "syn_13", group: "agreement", kind: "interpretation", confidence: "high", text: "The perspectives that reviewed your case agree that the missing MRI report is the most important gap.", derivedFrom: ["mxk1"] },
      { id: "syn_14", group: "clarification", kind: "interpretation", confidence: "low", flag: "uncertain", impact: "medium", text: "The medicine-safety review could not be completed for this report. Your ibuprofen use was raised by General Medicine only, so it has not been double-checked.", derivedFrom: ["sr_ms", "mxk3"] },
      { id: "syn_15", group: "clarification", kind: "interpretation", confidence: "moderate", impact: "medium", text: "You have taken ibuprofen regularly for about three months. It may be worth reviewing this with your prescriber. Please do not change any medicine on your own.", derivedFrom: ["gk2", "clk1"] },
      { id: "syn_16", group: "clarification", kind: "interpretation", confidence: "moderate", impact: "high", text: "Before deciding, it may help to get the written MRI report and ask how much non-surgical care is usually tried first.", derivedFrom: ["syn_10", "syn_11"] },
    ],
  },
  reportPlan: {
    s1: ["syn_1"],
    s2: ["syn_2", "syn_3"],
    s4: ["syn_4"],
    s6: ["syn_5"],
    s7: ["syn_6"],
    s8: ["syn_7"],
    s9: ["syn_8", "syn_9"],
    s10: ["syn_10", "syn_11", "syn_12"],
    s11: ["syn_14", "syn_15"],
    s13: ["syn_13"],
    s17: ["syn_16"],
  },
  questions: [
    { id: "q1", audience: "current_doctor", priority: 1, category: "Testing", text: "Can I have a copy of the written MRI report? Does it confirm a meniscus tear?", trigger: "No written MRI report is in your records, and it is the main thing that would confirm the tear.", linkedItemIds: ["syn_10", "mxk1"], status: "not_asked" },
    { id: "q2", audience: "current_doctor", priority: 1, category: "Alternatives", text: "How much non-surgical treatment do you usually try first, and would a longer physiotherapy trial be reasonable in my case?", trigger: "Only two physiotherapy sessions are recorded.", linkedItemIds: ["syn_11", "syn_9"], status: "not_asked" },
    { id: "q3", audience: "current_doctor", priority: 2, category: "Diagnosis", text: "Is my pain more likely to come from a tear or from wear in the joint, and how can we tell?", trigger: "The records don't separate these two causes.", linkedItemIds: ["syn_8", "oku2"], status: "not_asked" },
    { id: "q4", audience: "current_doctor", priority: 3, category: "Medicines", text: "I've taken ibuprofen three times a day for about three months. Should we review that?", trigger: "Regular ibuprofen use was raised by General Medicine.", linkedItemIds: ["syn_15", "gk2"], status: "not_asked" },
    { id: "q5", audience: "second_opinion_doctor", priority: 1, category: "Testing", text: "Having seen the MRI, do you see a tear that matches my symptoms of catching?", trigger: "A second reading of the missing MRI would address the main gap.", linkedItemIds: ["syn_10"], status: "not_asked" },
    { id: "q6", audience: "second_opinion_doctor", priority: 2, category: "Timing", text: "If I try non-surgical care first, what would tell us it is time to reconsider surgery?", trigger: "Helps you plan around the uncertainty rather than decide now.", linkedItemIds: ["syn_16", "syn_7"], status: "not_asked" },
  ],
  secondOpinionDocName: "Second-opinion orthopaedic note (synthetic).pdf",
  secondOpinionFacts: [
    { id: "so_k1", type: "recommendation", label: "Second opinion: obtain the written MRI report", date: "2026-09-25", confidence: 0.9, source: src("d_so", 1, "Plan", "Obtain written MRI report before deciding on surgery.") },
    { id: "so_k2", type: "recommendation", label: "Second opinion: 6-week physiotherapy trial", date: "2026-09-25", confidence: 0.9, source: src("d_so", 1, "Plan", "Structured physiotherapy for 6 weeks, then review.") },
    { id: "so_k3", type: "recommendation", label: "Second opinion: surgery may be reconsidered if catching persists", date: "2026-09-25", confidence: 0.88, source: src("d_so", 2, "Plan", "If mechanical symptoms persist, keyhole surgery can be reconsidered.") },
  ],
  comparison: {
    opinionALabel: "Your treating surgeon",
    opinionBLabel: "Second-opinion doctor",
    rows: [
      { id: "cmp1", topic: "Surgery now", opinionA: "Advises keyhole surgery on the right knee.", opinionB: "Suggests deciding after the MRI report and a 6-week physiotherapy trial.", evidenceA: ["f_k5"], evidenceB: ["so_k2"], relationship: "differs", itemIds: ["syn_6", "so_k2"] },
      { id: "cmp2", topic: "MRI report", opinionA: "Reviewed in clinic. No written report in your records.", opinionB: "Asks for the written MRI report.", evidenceA: ["f_k4"], evidenceB: ["so_k1"], relationship: "new_info", itemIds: ["syn_10", "so_k1"] },
      { id: "cmp3", topic: "Non-surgical care", opinionA: "Two physiotherapy sessions recorded.", opinionB: "Proposes a structured 6-week trial.", evidenceA: ["f_k3"], evidenceB: ["so_k2"], relationship: "changed", itemIds: ["syn_11", "so_k2"] },
      { id: "cmp4", topic: "If catching continues", opinionA: "Not discussed in writing.", opinionB: "Surgery can be reconsidered.", evidenceA: [], evidenceB: ["so_k3"], relationship: "agreement", itemIds: ["syn_7", "so_k3"] },
      { id: "cmp5", topic: "Regular ibuprofen", opinionA: "Not discussed.", opinionB: "Not discussed.", evidenceA: [], evidenceB: [], relationship: "unresolved", itemIds: ["syn_15"] },
    ],
    nextQuestions: [
      { audience: "Your current doctor", text: "Your second-opinion doctor suggests a 6-week physiotherapy trial first. Would that change your plan?", itemIds: ["cmp1"] },
      { audience: "Either doctor", text: "Neither opinion mentions regular ibuprofen. Could we review it?", itemIds: ["cmp5"] },
    ],
    answeredByOpinion: [{ questionId: "q2", note: "The second opinion proposes a 6-week physiotherapy trial.", status: "partially_answered" }],
  },
  highlights: [
    { id: "syn_6", text: "Keyhole surgery on the right knee has been advised." },
    { id: "syn_10", text: "No written MRI report is in your records.", flag: "missing" },
    { id: "syn_4", text: "A meniscus tear is suspected, but not confirmed.", flag: "uncertain" },
    { id: "syn_14", text: "The medicine-safety review could not be completed.", flag: "uncertain" },
  ],
  runWarnings: [
    "One document (the MRI photo) could not be read. A clear copy of the written MRI report would help.",
    "The Medication Safety perspective did not finish. The report continues without it and says so.",
  ],
  stepNotes: {
    2: "One file couldn't be read clearly.",
    4: "One X-ray value is marked uncertain.",
    7: "Medication Safety didn't finish; continuing without it.",
  },
  finalStatus: "partial",
};
