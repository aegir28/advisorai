"""Deterministic checks on a specialty agent's output. This is a CONTRACT check, not a medical one: it
verifies
that a report is internally consistent and that everything it cites exists in what the agent was given. It
cannot, and does not try to, judge whether the content is clinically right.

A report that fails is not shown; the caller turns it into an `incomplete`/`failed` outcome (never silent).
"""

from dataclasses import dataclass

from app.agents.contracts import AgentSpec, SpecialtyInput
from app.safety.output_lint import lint_document
from app.schemas.case import CaseV1
from app.schemas.medication_review import MedicationReview
from app.schemas.specialist_report import SpecialistReport

# Codes worth surfacing that do not make a report unusable.
WARNING_CODES = frozenset({"limitations_missing"})


@dataclass(frozen=True, slots=True)
class Violation:
    code: str
    ref: str = ""

    @property
    def is_error(self) -> bool:
        return self.code not in WARNING_CODES

    def __str__(self) -> str:
        return f"{self.code}:{self.ref}" if self.ref else self.code


def case_fact_refs(case: CaseV1) -> set[str]:
    """Every `fact_ref` the structured case carries: the only fact ids an agent may cite."""
    refs: set[str] = set()
    for group in (
        case.symptoms,
        case.diagnoses,
        case.history,
        case.allergies,
        case.medications,
        case.procedures,
        case.surgeries,
        case.treatment_history,
        case.recommendations,
        case.investigations.labs,
        case.investigations.imaging,
        case.investigations.ecg,
        case.investigations.pathology,
    ):
        refs.update(item.fact_ref for item in group)
    return refs


def errors(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.is_error]


def validate_specialist_report(
    report: SpecialistReport, payload: SpecialtyInput, spec: AgentSpec
) -> list[Violation]:
    out: list[Violation] = []

    if report.specialist != spec.id:
        out.append(Violation("specialist_mismatch", report.specialist))
    if report.case_id != payload.case.case_id:
        out.append(Violation("case_mismatch"))
    if report.run_id != payload.run_id:
        out.append(Violation("run_mismatch"))
    if report.version != spec.version or report.tier != spec.tier:
        out.append(Violation("agent_metadata_mismatch"))

    facts = case_fact_refs(payload.case)
    source_ids = {s.id for s in payload.sources}

    findings = [*report.findings, *report.considerations]
    owned_ids = (
        [f.id for f in findings]
        + [u.id for u in report.uncertainties]
        + [m.id for m in report.missing_info]
        + [c.id for c in report.contradictions]
        + [q.id for q in report.questions]
    )
    seen: set[str] = set()
    for item_id in owned_ids:
        if item_id in seen:
            out.append(Violation("duplicate_id", item_id))
        seen.add(item_id)

    for finding in findings:
        for ref in finding.fact_refs:
            if ref not in facts:
                out.append(Violation("unknown_fact_ref", ref))
        if finding.kind == "patient_fact" and not finding.fact_refs:
            out.append(Violation("patient_fact_untraced", finding.id))
        if finding.kind == "external_evidence":
            if not finding.source_ids:
                out.append(Violation("external_evidence_unsourced", finding.id))
            for sid in finding.source_ids or []:
                if sid not in source_ids:
                    out.append(Violation("unknown_source", sid))

    for evidence in report.evidence_refs:
        if evidence.source_id not in source_ids:
            out.append(Violation("unknown_source", evidence.source_id))

    linkable = (
        {f.id for f in findings}
        | {u.id for u in report.uncertainties}
        | {m.id for m in report.missing_info}
        | {c.id for c in report.contradictions}
    )
    # A contradiction is between things in the record (fact ids) or between the agent's own statements.
    for contradiction in report.contradictions:
        for ref in contradiction.between:
            if ref not in linkable and ref not in facts:
                out.append(Violation("contradiction_unknown_ref", ref))
    for question in report.questions:
        if not question.linked_to:
            out.append(Violation("question_unlinked", question.id))
        for ref in question.linked_to:
            if ref not in linkable:
                out.append(Violation("question_unknown_ref", ref))

    if not report.limitations:
        out.append(Violation("limitations_missing"))
    if not report.confidence.reason.strip():
        out.append(Violation("confidence_unexplained"))
    if report.status != "complete" and not (report.status_note or "").strip():
        out.append(Violation("status_note_missing"))
    return out


def validate_medication_review(
    review: MedicationReview, case: CaseV1, source_ids: set[str]
) -> list[Violation]:
    """Contract + safety checks on a Medication Safety output. Deterministic; judges no medicine."""
    out: list[Violation] = []
    facts = case_fact_refs(case)
    med_fact_refs = {m.fact_ref for m in case.medications}
    medicine_ids = {m.id for m in review.medicines}
    concern_ids = {c.id for c in review.concerns}

    ids = (
        [m.id for m in review.medicines]
        + [c.id for c in review.concerns]
        + [d.id for d in review.discussion_points]
    )
    if len(set(ids)) != len(ids):
        out.append(Violation("duplicate_id"))
    reviewed = {ref for m in review.medicines for ref in m.fact_refs}
    for ref in sorted(med_fact_refs - reviewed):
        out.append(Violation("medication_not_reviewed", ref))
    for medicine in review.medicines:
        for ref in medicine.fact_refs:
            if ref not in med_fact_refs:
                out.append(Violation("medicine_fact_not_a_medication", ref))
    for concern in review.concerns:
        for mid in concern.medication_ids:
            if mid not in medicine_ids:
                out.append(Violation("concern_unknown_medicine", mid))
        for ref in concern.fact_refs:
            if ref not in facts:
                out.append(Violation("unknown_fact_ref", ref))
        for sid in concern.source_ids:
            if sid not in source_ids:
                out.append(Violation("unknown_source", sid))
    for point in review.discussion_points:
        for ref in point.linked_to:
            if ref not in medicine_ids | concern_ids:
                out.append(Violation("discussion_unknown_ref", ref))
    for key, violation in lint_document(review.model_dump(mode="json")):
        out.append(Violation(f"unsafe_text:{violation.rule}", key))
    return out
