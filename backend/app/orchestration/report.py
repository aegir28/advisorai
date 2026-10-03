"""The 19-section patient report, assembled deterministically from stage artifacts.

Nothing is invented here. Every non-template item is a synthesis item, a specialist finding, a question or a
record item that already carries its evidence ids; section text for anything unavailable is a fixed honest
note. Model-written text was linted when it entered the synthesis; the final report is linted again as a whole
(`lint_document`), and its reading level is measured, so a unsafe or too-hard report is caught before anyone
sees it.
"""

from datetime import UTC, datetime

from app.orchestration.contracts import CaseContext, RunSummary, SynthesisArtifact
from app.orchestration.review import SECTIONS_FOR_GROUP
from app.orchestration.wire import make
from app.safety.output_lint import lint_document
from app.safety.readability import grade_level
from app.schemas.common import Confidence
from app.schemas.questions import Question
from app.schemas.report import (
    REPORT_SCHEMA_VERSION,
    PatientReport,
    ReportItem,
    ReportSection,
    ReportSectionType,
)
from app.schemas.specialist_report import SpecialistReport

DISCLAIMER = (
    "This report helps you prepare for a conversation with a doctor. It was made by AI from the documents you "
    "shared. It is not a diagnosis and not medical advice, and it is not a doctor's opinion. Do not start, "
    "stop or change any medicine because of this report. Talk to a doctor who knows you."
)
_EMPTY: dict[int, str] = {
    1: "There was not enough in your records to write a summary.",
    2: "No clear points from your documents were found.",
    4: "Nothing further was found in your history.",
    6: "No medicine points were found.",
    7: "No treatment points were found.",
    8: "No points to explain were found.",
    9: "The analysis did not flag anything it was unsure about.",
    10: "No missing items were identified.",
    11: "No further points to clarify were found.",
    13: "No clear areas of agreement were found.",
    14: "No disagreements between the perspectives were found.",
    15: "No questions for your current doctor were generated.",
    16: "No questions for a second-opinion doctor were generated.",
    17: "No further points were found.",
}
_TYPES: dict[int, ReportSectionType] = {
    1: "prose",
    2: "bullets",
    3: "timeline",
    4: "bullets",
    5: "medicines",
    6: "bullets",
    7: "bullets",
    8: "bullets",
    9: "bullets",
    10: "bullets",
    11: "bullets",
    12: "perspectives",
    13: "agreements",
    14: "disagreements",
    15: "questions",
    16: "questions",
    17: "bullets",
    18: "references",
    19: "disclaimer",
}


def _note(text: str) -> ReportItem:
    return make(ReportItem, text=text, kind="template", evidence_ids=[])


def _section_for(group: str, hint: int | None) -> int:
    allowed = SECTIONS_FOR_GROUP.get(group, (17,))
    return hint if hint in allowed and hint is not None else allowed[0]


def assemble_report(
    *,
    report_id: str,
    case_id: str,
    run_id: str,
    context: CaseContext,
    synthesis: SynthesisArtifact,
    reports: list[SpecialistReport],
    questions: list[Question],
    summary: RunSummary,
    source_titles: dict[str, str],
    removed_claim_ids: set[str] | frozenset[str] = frozenset(),
    now: datetime | None = None,
) -> PatientReport:
    buckets: dict[int, list[ReportItem]] = {n: [] for n in range(1, 20)}

    for item in synthesis.synthesis.items:
        n = _section_for(item.group, synthesis.section_hints.get(item.id))
        buckets[n].append(
            make(
                ReportItem,
                id=item.id,
                text=item.text,
                kind=item.kind,
                flag=item.flag,
                evidence_ids=list(item.derived_from),
                meta={"confidence": item.confidence},
            )
        )
    for entry in context.timeline:
        buckets[3].append(
            make(
                ReportItem,
                id=entry.id,
                text=entry.title,
                kind="patient_fact",
                evidence_ids=[f"ev_{entry.fact_id}"],
                meta={"date": entry.date},
            )
        )
    for med in context.case.medications:
        if med.fact_ref:
            buckets[5].append(
                make(
                    ReportItem,
                    id=f"med_{med.fact_ref}",
                    text=med.name,
                    kind="patient_fact",
                    evidence_ids=[f"ev_{med.fact_ref}"],
                    meta={"dose": med.dose or ""},
                )
            )
    for r in reports:
        conf: Confidence = r.confidence.overall
        top = sorted(
            (f for f in r.findings if f"cl_{r.specialist}_{f.id}" not in removed_claim_ids),
            key=lambda f: {"high": 0, "medium": 1, "low": 2}[f.importance],
        )[:2]
        for f in top:
            if f"cl_{r.specialist}_{f.id}" in removed_claim_ids:
                continue  # an unsupported claim never reaches the report, whatever section it would be in
            buckets[12].append(
                make(
                    ReportItem,
                    id=f"persp_{r.specialist}_{f.id}",
                    text=f.statement,
                    kind=f.kind,
                    evidence_ids=[f.id],
                    meta={"specialist": r.name, "confidence": conf},
                )
            )
    for agent in summary.agents_unavailable:
        buckets[12].append(
            make(
                ReportItem,
                text=f"The {agent.replace('_', ' ')} perspective could not be completed, so it is not included.",
                kind="template",
                flag="uncertain",
                evidence_ids=[],
            )
        )
    for q in questions:
        n = 15 if q.audience == "current_doctor" else 16
        buckets[n].append(
            make(
                ReportItem,
                id=q.id,
                text=q.text,
                kind="interpretation",
                evidence_ids=list(q.linked_item_ids),
                meta={"priority": str(q.priority), "category": q.category},
            )
        )
    used = {e for item in synthesis.synthesis.items for e in item.derived_from}
    for r in reports:
        for ref in r.evidence_refs:
            if ref.source_id in source_titles and ref.source_id not in {i.id for i in buckets[18]}:
                buckets[18].append(
                    make(
                        ReportItem,
                        id=ref.source_id,
                        text=source_titles[ref.source_id],
                        kind="external_evidence",
                        evidence_ids=[ref.source_id],
                    )
                )
    del used
    if summary.unreadable_documents:
        buckets[10].append(
            _note(
                f"{summary.unreadable_documents} of your documents could not be read (they are images "
                "without readable text), so nothing from them is included."
            )
        )
    if summary.missing_info_branch:
        buckets[10].append(_note("Few details could be read from your records, so this report is limited."))
    buckets[19] = [_note(DISCLAIMER)]

    sections: list[ReportSection] = []
    for n in range(1, 20):
        items = buckets[n]
        if not items and n in _EMPTY:
            items = [_note(_EMPTY[n])]
        sections.append(
            make(
                ReportSection,
                number=n,
                type=_TYPES[n],
                items=items,
                question_audience="current_doctor"
                if n == 15
                else "second_opinion_doctor"
                if n == 16
                else None,
            )
        )
    stamp = (now or datetime.now(UTC)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return PatientReport(
        schema_version=REPORT_SCHEMA_VERSION,  # type: ignore[arg-type]
        id=report_id,
        case_id=case_id,
        run_id=run_id,
        generated_at=stamp,
        sections=sections,
    )


def report_safety(report: PatientReport) -> list[str]:
    """Violation codes (never text) found when the whole report is linted."""
    return sorted({v.rule for _, v in lint_document(report.model_dump(mode="json"))})


def report_grade(report: PatientReport) -> float:
    prose = " ".join(
        i.text for s in report.sections if s.number != 19 for i in s.items if i.kind != "template"
    )
    return grade_level(prose)
