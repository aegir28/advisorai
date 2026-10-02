"""case.v1: the canonical structured case the backend stores and hands to agents.

Identity fields (names, phone, email, hospital IDs) are never part of it: agents see
pseudonymous slices only.
"""

from typing import Annotated, Any, Literal

from pydantic import Field

from .common import Id, IsoDate, Sex, WireModel

CASE_SCHEMA_VERSION = "case.v1"


class FactItem(WireModel):
    text: str
    fact_ref: Id


class InvestigationItem(WireModel):
    name: str
    value: str | None = None
    flag: str | None = None
    date: IsoDate
    fact_ref: Id


class Demographics(WireModel):
    age: Annotated[int, Field(ge=0, le=120)]
    sex: Sex


class Symptom(WireModel):
    text: str
    onset: str | None = None
    fact_ref: Id


class Diagnosis(WireModel):
    name: str
    status: Literal["documented", "suspected"]
    fact_ref: Id


class Medication(WireModel):
    name: str
    dose: str | None = None
    freq: str | None = None
    start: str | None = None
    fact_ref: Id


class Investigations(WireModel):
    labs: list[InvestigationItem]
    imaging: list[InvestigationItem]
    ecg: list[InvestigationItem]
    pathology: list[InvestigationItem]


class Recommendation(WireModel):
    by: str
    text: str
    fact_ref: Id


class Proposed(WireModel):
    treatment: list[str]
    procedure: list[str]


class MissingInformation(WireModel):
    item: str
    why_matters: str


class CaseV1(WireModel):
    schema_version: Literal["case.v1"]
    case_id: Id
    demographics: Demographics
    chief_concern: str
    symptoms: list[Symptom]
    diagnoses: list[Diagnosis]
    history: list[FactItem]
    allergies: list[FactItem]
    medications: list[Medication]
    investigations: Investigations
    procedures: list[FactItem]
    surgeries: list[FactItem]
    treatment_history: list[FactItem]
    recommendations: list[Recommendation]
    proposed: Proposed
    timeline_ref: Id
    unresolved_questions: list[str]
    missing_information: list[MissingInformation]
    evidence_refs: list[Id]
    extensions: dict[str, Any]
