import type {
  CaseSummary,
  EvidenceRef,
  Claim,
  Comparison,
  DocumentItem,
  ExternalSource,
  Fact,
  MatrixRow,
  Question,
  RoutingPlan,
  ScenarioId,
  SourceRef,
  SpecialistReport,
  Synthesis,
  TimelineData,
} from "@/domain/types";

/** Which synthesis items feed each plain-language report section. */
export interface ReportPlan {
  s1: string[];
  s2: string[];
  s4: string[];
  s6: string[];
  s7: string[];
  s8: string[];
  s9: string[];
  s10: string[];
  s11: string[];
  s13: string[];
  s17: string[];
}

/**
 * Everything the (future) backend would compute for one analysed case.
 * Mock scenarios implement this; the backend will return the same shapes.
 */
export interface ScenarioData {
  id: ScenarioId;
  seedCase: CaseSummary;
  documents: DocumentItem[];
  facts: Fact[];
  timeline: TimelineData;
  routing: RoutingPlan;
  specialists: SpecialistReport[];
  matrix: MatrixRow[];
  claims: Claim[];
  sources: ExternalSource[];
  synthesis: Synthesis;
  reportPlan: ReportPlan;
  questions: Question[];
  comparison: Comparison;
  secondOpinionDocName: string;
  /** Facts extracted from the second-opinion document once it is uploaded. */
  secondOpinionFacts: Fact[];
  highlights: { id: string; text: string; flag?: "uncertain" | "missing" | "disagreement" }[];
  /** Notes shown on the progress screen when the run finishes with gaps. */
  runWarnings: string[];
  /** Step notes for runs that finish with a note. */
  stepNotes: Partial<Record<number, string>>;
  finalStatus: "complete" | "partial";
}

export const src = (docId: string, page: number, section: string, snippet: string): SourceRef => ({
  docId,
  page,
  section,
  snippet,
});

/** Build `evidence_refs` for a specialist report from the sources it relied on. */
export function evidenceRefs(sources: ExternalSource[], ...ids: string[]): EvidenceRef[] {
  return ids.map((id) => {
    const s = sources.find((x) => x.id === id);
    if (!s) throw new Error(`Unknown evidence source in fixture: ${id}`);
    return { sourceId: s.id, title: s.title, section: s.section };
  });
}
