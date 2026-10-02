import type {
  CaseV1,
  Claim,
  CrossReviewData,
  EvidenceData,
  Fact,
  PatientReport,
  PerspectivesData,
  ReportItem,
  ReportSection,
  SpecialistId,
  SynthesisItem,
  Trace,
  TraceNode,
} from "@/domain/types";
import { SCHEMA_VERSIONS } from "@/domain/schemas";
import { t } from "@/i18n";
import { specialistNames } from "./scenarios";
import type { ScenarioData } from "./scenarios/types";

/**
 * Derived-data builders. In the real system the backend computes these and
 * stores them; here we derive them from the scenario so there is exactly one
 * source of truth per case.
 */

const MAX_DEPTH = 5;

function formatFactText(f: Fact): string {
  return f.value ? `${f.label}: ${f.value}` : f.label;
}

export function buildTrace(sc: ScenarioData, itemId: string): Trace | null {
  const node = resolve(sc, itemId, 0, new Set());
  return node ? { schema_version: SCHEMA_VERSIONS.trace, itemId, root: node } : null;
}

function resolve(sc: ScenarioData, id: string, depth: number, seen: Set<string>): TraceNode | null {
  if (depth > MAX_DEPTH || seen.has(id)) return null;
  const nextSeen = new Set(seen).add(id);
  const kids = (ids: string[]) =>
    ids.map((x) => resolve(sc, x, depth + 1, nextSeen)).filter((n): n is TraceNode => n !== null);

  // Synthesis item (also the report sentence ID)
  const syn = sc.synthesis.items.find((i) => i.id === id);
  if (syn) {
    return { id, level: "synthesis", text: syn.text, kind: syn.kind, flag: syn.flag, label: "AI review summary item", children: kids(syn.derivedFrom) };
  }

  // Facts (including facts from a second-opinion document)
  const fact = [...sc.facts, ...sc.secondOpinionFacts].find((f) => f.id === id);
  if (fact) {
    return { id, level: "fact", text: formatFactText(fact), kind: "patient_fact", label: "Fact from your records", source: fact.source, children: [] };
  }

  // Timeline events and gaps
  const ev = sc.timeline.events.find((e) => e.id === id);
  if (ev) {
    return { id, level: "timeline", text: `${ev.title}. ${ev.detail}`, kind: "patient_fact", flag: ev.conflict ? "disagreement" : undefined, label: "Timeline event", children: kids([ev.factId]) };
  }
  const gap = sc.timeline.gaps.find((g) => g.id === id);
  if (gap) {
    return { id, level: "timeline", text: gap.text, kind: "interpretation", flag: "missing", label: "Timeline check", children: kids([gap.afterEventId]) };
  }

  // Specialist reports and their parts
  const report = sc.specialists.find((r) => r.id === id);
  if (report) {
    return { id, level: "specialist", text: `${report.name} perspective (v${report.version}). ${report.confidence.reason}`, kind: "interpretation", flag: report.status !== "complete" ? "uncertain" : undefined, label: report.name, children: [] };
  }
  for (const r of sc.specialists) {
    const finding = [...r.findings, ...r.considerations].find((f) => f.id === id);
    if (finding) {
      return {
        id, level: "specialist", text: finding.statement, kind: finding.kind, label: `${r.name} perspective`,
        children: [...kids(finding.factRefs), ...kids(finding.sourceIds ?? [])],
      };
    }
    const unc = r.uncertainties.find((u) => u.id === id);
    if (unc) return { id, level: "specialist", text: unc.text, kind: "interpretation", flag: "uncertain", label: `${r.name} perspective`, children: [] };
    const miss = r.missing_info.find((m) => m.id === id);
    if (miss) return { id, level: "specialist", text: `${miss.item}. ${miss.whyItMatters}`, kind: "interpretation", flag: "missing", label: `${r.name} perspective`, children: [] };
    const con = r.contradictions.find((c) => c.id === id);
    if (con) return { id, level: "specialist", text: con.description, kind: "interpretation", flag: "disagreement", label: `${r.name} perspective`, children: kids(con.between) };
  }

  // Cross-review rows
  const row = sc.matrix.find((m) => m.id === id);
  if (row) {
    return { id, level: "matrix", text: `${row.topic}. ${row.summary}`, kind: "interpretation", flag: row.relationship === "disagreement" ? "disagreement" : row.relationship === "missing_info" ? "missing" : undefined, label: "Cross-review", children: kids(row.itemIds) };
  }

  // Verified claims
  const claim = sc.claims.find((c) => c.id === id);
  if (claim) {
    return { id, level: "verification", text: claim.text, kind: claim.kind, status: claim.status, label: claim.removed ? "Claim removed before the report" : "Claim check", children: [...kids(claim.patientFactIds), ...kids(claim.externalSourceIds)] };
  }

  // External evidence sources
  const source = sc.sources.find((s) => s.id === id);
  if (source) {
    return { id, level: "evidence_source", text: source.title, kind: "external_evidence", label: "Reference evidence", externalSource: source, children: [] };
  }

  // Questions and comparison rows
  const q = sc.questions.find((x) => x.id === id);
  if (q) return { id, level: "question", text: q.text, kind: "interpretation", label: "Question", children: kids(q.linkedItemIds) };
  const cmp = sc.comparison.rows.find((x) => x.id === id);
  if (cmp) return { id, level: "comparison", text: `${cmp.topic}. A: ${cmp.opinionA} B: ${cmp.opinionB}`, kind: "interpretation", label: "Comparison", children: kids([...cmp.evidenceA, ...cmp.evidenceB, ...cmp.itemIds]) };

  return null;
}

// ── Report ───────────────────────────────────────────────

const toItem = (s: SynthesisItem): ReportItem => ({ id: s.id, text: s.text, kind: s.kind, flag: s.flag, evidenceIds: [s.id] });

export function buildReport(sc: ScenarioData, caseId: string, runId: string, generatedAt: string): PatientReport {
  const byId = (ids: string[]) => ids.map((i) => sc.synthesis.items.find((s) => s.id === i)).filter((s): s is SynthesisItem => !!s).map(toItem);
  const p = sc.reportPlan;
  const pick = (g: SynthesisItem["group"]) => sc.synthesis.items.filter((s) => s.group === g).map(toItem);

  const meds = sc.facts.filter((f) => f.type === "medication");
  const timeline: ReportItem[] = [
    ...sc.timeline.events.map<ReportItem>((e) => ({
      id: e.id, text: `${e.title}. ${e.detail}`, kind: "patient_fact", flag: e.conflict ? "disagreement" : undefined, evidenceIds: [e.id], meta: { date: e.date, precision: e.precision },
    })),
    ...sc.timeline.gaps.map<ReportItem>((g) => ({ id: g.id, text: g.text, kind: "interpretation", flag: "missing", evidenceIds: [g.id], meta: { gap: "true" } })),
  ];

  const perspectives: ReportItem[] = sc.specialists.flatMap<ReportItem>((r) => {
    if (r.status !== "complete") {
      return [{ id: r.id, text: r.statusNote ?? "This perspective did not finish.", kind: "interpretation", flag: "uncertain", evidenceIds: [r.id], meta: { specialist: r.name, confidence: r.confidence.overall } }];
    }
    return [...r.findings]
      .sort((a, b) => ({ high: 0, medium: 1, low: 2 })[a.importance] - ({ high: 0, medium: 1, low: 2 })[b.importance])
      .slice(0, 2)
      .map<ReportItem>((f) => ({ id: f.id, text: f.statement, kind: f.kind, evidenceIds: [f.id], meta: { specialist: r.name, confidence: r.confidence.overall } }));
  });

  const disagreements = pick("disagreement");
  const agreements = byId(p.s13);
  const missing = byId(p.s10);

  const usedSourceIds = new Set(sc.claims.filter((c) => !c.removed).flatMap((c) => c.externalSourceIds));
  const references: ReportItem[] = sc.sources
    .filter((s) => usedSourceIds.has(s.id))
    .map((s) => ({ id: s.id, text: `${s.title}. ${s.publisher}, ${s.year}`, kind: "external_evidence", evidenceIds: [s.id] }));

  const template = (key: Parameters<typeof t>[0]): ReportItem => ({ text: t(key), kind: "template", evidenceIds: [] });
  const note = (text: string): ReportItem => ({ text, kind: "template", evidenceIds: [] });

  const sections: ReportSection[] = [
    { number: 1, type: "prose", items: byId(p.s1) },
    { number: 2, type: "bullets", items: byId(p.s2) },
    { number: 3, type: "timeline", items: timeline },
    { number: 4, type: "bullets", items: byId(p.s4) },
    {
      number: 5, type: "medicines",
      items: meds.map<ReportItem>((m) => ({ id: m.id, text: m.label, kind: "patient_fact", evidenceIds: [m.id], meta: { dose: m.value ?? "" } })),
    },
    { number: 6, type: "bullets", items: byId(p.s6) },
    { number: 7, type: "bullets", items: byId(p.s7) },
    { number: 8, type: "bullets", items: byId(p.s8) },
    { number: 9, type: "bullets", items: byId(p.s9) },
    { number: 10, type: "bullets", items: missing.length ? missing : [note("No missing items were identified.")] },
    { number: 11, type: "bullets", items: byId(p.s11.filter((i) => sc.synthesis.items.find((s) => s.id === i)?.group !== "disagreement")) },
    { number: 12, type: "perspectives", items: perspectives },
    { number: 13, type: "agreements", items: agreements.length ? agreements : [note("No clear areas of agreement were found.")] },
    {
      number: 14, type: "disagreements",
      items: disagreements.length ? disagreements : [note("No disagreements between the perspectives were found. Perspectives that could not finish are listed in the section on specialist perspectives.")],
    },
    { number: 15, type: "questions", questionAudience: "current_doctor", items: sc.questions.filter((q) => q.audience === "current_doctor").map(qToItem) },
    { number: 16, type: "questions", questionAudience: "second_opinion_doctor", items: sc.questions.filter((q) => q.audience === "second_opinion_doctor").map(qToItem) },
    { number: 17, type: "bullets", items: byId(p.s17) },
    { number: 18, type: "references", items: references },
    { number: 19, type: "disclaimer", items: [template("disclaimer.long")] },
  ];

  return { schema_version: SCHEMA_VERSIONS.report, id: `rep_${runId}`, caseId, runId, generatedAt, sections };
}

function qToItem(q: ScenarioData["questions"][number]): ReportItem {
  return { id: q.id, text: q.text, kind: "interpretation", evidenceIds: [q.id], meta: { priority: String(q.priority), category: q.category } };
}

// ── Aggregates ───────────────────────────────────────────

/**
 * Specialist reports carry the real case and run they belong to. Fixtures are
 * authored against the seeded case, so they are re-stamped for any other case
 * that reuses the same synthetic scenario.
 */
export function buildPerspectives(sc: ScenarioData, caseId: string, runId: string): PerspectivesData {
  return { routing: sc.routing, reports: sc.specialists.map((r) => ({ ...r, case_id: caseId, run_id: runId })) };
}

export function buildEvidence(sc: ScenarioData): EvidenceData {
  return { claims: sc.claims, sources: sc.sources };
}

export function summariseClaims(claims: Claim[]) {
  const byStatus = { supported: 0, partially_supported: 0, unclear: 0, contradicted: 0, insufficient_evidence: 0 };
  let removed = 0;
  for (const c of claims) {
    byStatus[c.status] += 1;
    if (c.removed) removed += 1;
  }
  return { total: claims.length, byStatus, removed };
}

export function buildCrossReview(sc: ScenarioData): CrossReviewData {
  const ids = new Set<SpecialistId>();
  sc.matrix.forEach((r) => Object.keys(r.cells).forEach((k) => ids.add(k as SpecialistId)));
  const ordered = sc.specialists.map((s) => s.specialist).filter((s) => ids.has(s));
  return { specialists: ordered.map((id) => ({ id, name: specialistNames[id] })), rows: sc.matrix };
}

// ── case.v1 ──────────────────────────────────────────────

/**
 * Derive the canonical structured case from the extracted facts. The backend
 * will produce this from document intelligence. It never contains names or any
 * identity field, only a pseudonymous case ID, age and sex.
 */
export function buildCaseV1(sc: ScenarioData, caseId: string): CaseV1 {
  const c = sc.seedCase;
  const byType = (type: Fact["type"]) => sc.facts.filter((f) => f.type === type);
  const item = (f: Fact) => ({ text: f.value ? `${f.label}: ${f.value}` : f.label, fact_ref: f.id });
  const test = (f: Fact) => ({ name: f.label, value: f.value, flag: f.flag, date: f.date, fact_ref: f.id });

  const missing = new Map<string, string>();
  for (const r of sc.specialists) for (const m of r.missing_info) if (!missing.has(m.item)) missing.set(m.item, m.whyItMatters);

  return {
    schema_version: SCHEMA_VERSIONS.case,
    case_id: caseId,
    demographics: { age: c.ageYears, sex: c.sex },
    chief_concern: c.concern,
    symptoms: byType("symptom").map((f) => ({ text: f.value ? `${f.label}: ${f.value}` : f.label, onset: f.date, fact_ref: f.id })),
    diagnoses: byType("diagnosis").map((f) => ({
      name: f.label,
      status: /suspected/i.test(`${f.label} ${f.value ?? ""}`) ? ("suspected" as const) : ("documented" as const),
      fact_ref: f.id,
    })),
    history: [],
    allergies: [],
    medications: byType("medication").map((f) => ({ name: f.label, dose: f.value, start: f.date, fact_ref: f.id })),
    investigations: {
      labs: byType("lab_result").map(test),
      imaging: [...byType("imaging"), ...byType("procedure_finding")].map(test),
      ecg: byType("ecg").map(test),
      pathology: [],
    },
    procedures: [],
    surgeries: [],
    treatment_history: byType("treatment_history").map(item),
    recommendations: byType("recommendation").map((f) => ({ by: "treating clinician", text: f.value ? `${f.label}: ${f.value}` : f.label, fact_ref: f.id })),
    proposed: { treatment: [], procedure: c.proposedTreatment ? [c.proposedTreatment] : [] },
    timeline_ref: `tl_${caseId}`,
    unresolved_questions: sc.synthesis.items.filter((i) => i.group === "uncertainty").map((i) => i.text),
    missing_information: [...missing].map(([it, why]) => ({ item: it, why_matters: why })),
    evidence_refs: sc.facts.map((f) => f.id),
    extensions: {},
  };
}
