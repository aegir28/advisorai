"""Case structuring: build the structured, de-identified case context from what extraction found.

Deterministic: no model. Free text (the person's concern, fact text) is de-identified here, so `case.v1`
carries no identity, as its contract says. Facts keep their source (document, page, quote), and every fact
becomes an evidence item, so any later statement can be traced to a page.
"""

import re
from collections.abc import Sequence

from app.docintel.contracts import ExtractedFact
from app.evidence.contracts import EvidenceItem
from app.orchestration.contracts import CaseContext, DocumentBrief, TimelineEntry
from app.orchestration.store import CaseInputs
from app.safety.deidentify import deidentify
from app.schemas.case import (
    CaseV1,
    Demographics,
    Diagnosis,
    FactItem,
    InvestigationItem,
    Investigations,
    Medication,
    Proposed,
    Recommendation,
    Symptom,
)

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
_DMY = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b")
_MY = re.compile(r"\b([A-Za-z]{3,9})\.?,?\s+(\d{4})\b")
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )
}
_SUSPECTED = re.compile(r"\b(?:suspect\w*|possible|probable|likely|query|\?)", re.I)
_ECG = re.compile(r"\b(?:ecg|ekg|electrocardiogram)\b", re.I)


def clean(text: str) -> str:
    return deidentify(text).text


def to_iso_date(value: str | None) -> str | None:
    """An ISO date from what a document wrote ("2026-04-12", "12 April 2026", "April 2026"), else None."""
    if not value:
        return None
    if _ISO.match(value):
        return value[:10]
    if m := _DMY.search(value):
        month = _MONTHS.get(m.group(2)[:3].lower())
        if month:
            return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}"
    if m := _MY.search(value):
        month = _MONTHS.get(m.group(1)[:3].lower())
        if month:
            return f"{m.group(2)}-{month:02d}-01"
    return None


def _value(fact: ExtractedFact) -> str | None:
    parts = [p for p in (fact.value, fact.unit) if p]
    return clean(" ".join(parts)) if parts else None


def build_case_context(
    inputs: CaseInputs,
    facts: Sequence[ExtractedFact],
    documents: Sequence[DocumentBrief],
    unreadable_documents: int,
) -> CaseContext:
    symptoms: list[Symptom] = []
    diagnoses: list[Diagnosis] = []
    history: list[FactItem] = []
    allergies: list[FactItem] = []
    meds: list[Medication] = []
    procedures: list[FactItem] = []
    recs: list[Recommendation] = []
    labs: list[InvestigationItem] = []
    imaging: list[InvestigationItem] = []
    ecg: list[InvestigationItem] = []
    timeline: list[TimelineEntry] = []

    for fact in facts:
        text, iso = clean(fact.text), to_iso_date(fact.date)
        match fact.category:
            case "symptom":
                symptoms.append(Symptom(text=text, onset=fact.date and clean(fact.date), fact_ref=fact.id))
            case "diagnosis":
                diagnoses.append(
                    Diagnosis(
                        name=text,
                        status="suspected" if _SUSPECTED.search(fact.text) else "documented",
                        fact_ref=fact.id,
                    )
                )
            case "medication":
                meds.append(Medication(name=text, dose=_value(fact), fact_ref=fact.id))
            case "allergy":
                allergies.append(FactItem(text=text, fact_ref=fact.id))
            case "procedure":
                procedures.append(FactItem(text=text, fact_ref=fact.id))
            case "recommendation":
                recs.append(Recommendation(by="document", text=text, fact_ref=fact.id))
            case "lab_result" | "imaging_finding":
                if iso is None:
                    history.append(FactItem(text=text, fact_ref=fact.id))  # undated: kept as plain history
                else:
                    item = InvestigationItem(name=text, value=_value(fact), date=iso, fact_ref=fact.id)
                    if fact.category == "lab_result":
                        labs.append(item)
                    elif _ECG.search(fact.text):
                        ecg.append(item)
                    else:
                        imaging.append(item)
            case _:
                history.append(FactItem(text=text, fact_ref=fact.id))
        if iso is not None:
            timeline.append(TimelineEntry(id=f"tl_{fact.id}", date=iso, title=text[:120], fact_id=fact.id))
    timeline.sort(key=lambda e: (e.date, e.id))

    evidence = [
        EvidenceItem(id=f"ev_{f.id}", origin="patient_document", patient_source=f.source) for f in facts
    ]
    proposed = [clean(inputs.proposed_treatment)] if inputs.proposed_treatment else []
    case = CaseV1(
        schema_version="case.v1",
        case_id=str(inputs.case_id),
        demographics=Demographics(age=inputs.age_years, sex=inputs.sex),  # type: ignore[arg-type]
        chief_concern=clean(inputs.concern),
        symptoms=symptoms,
        diagnoses=diagnoses,
        history=history,
        allergies=allergies,
        medications=meds,
        investigations=Investigations(labs=labs, imaging=imaging, ecg=ecg, pathology=[]),
        procedures=procedures,
        surgeries=[],
        treatment_history=[],
        recommendations=recs,
        proposed=Proposed(treatment=proposed, procedure=[]),
        timeline_ref=f"timeline_{inputs.case_id}",
        unresolved_questions=[],
        missing_information=[],
        evidence_refs=[e.id for e in evidence],
        extensions={},
    )
    return CaseContext(
        schema_version="case_context.v1",
        case=case,
        evidence_index=evidence,
        documents=list(documents),
        timeline=timeline,
        unreadable_documents=unreadable_documents,
    )
