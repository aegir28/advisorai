"""report.v1: the patient-facing report. Exactly 19 sections; every claim is traceable."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .common import ContentKind, Flag, Id, IsoDate, NonEmpty, WireModel

REPORT_SCHEMA_VERSION = "report.v1"
SECTION_COUNT = 19

ReportSectionType = Literal[
    "prose",
    "bullets",
    "medicines",
    "timeline",
    "perspectives",
    "agreements",
    "disagreements",
    "questions",
    "references",
    "disclaimer",
]
QuestionAudience = Literal["current_doctor", "second_opinion_doctor"]


class ReportItem(WireModel):
    # Stable ID used for traceability. Only fixed template text has none.
    id: Id | None = None
    text: NonEmpty
    kind: ContentKind
    flag: Flag | None = None
    evidence_ids: list[Id]
    meta: dict[str, str] | None = None

    @model_validator(mode="after")
    def _non_template_items_are_traceable(self) -> Self:
        if self.kind != "template" and not (self.id and self.evidence_ids):
            raise ValueError("every non-template report item needs an id and at least one evidence ID")
        return self


class ReportSection(WireModel):
    number: Annotated[int, Field(ge=1, le=SECTION_COUNT)]
    type: ReportSectionType
    items: list[ReportItem]
    question_audience: QuestionAudience | None = None


class PatientReport(WireModel):
    schema_version: Literal["report.v1"]
    id: Id
    case_id: Id
    run_id: Id
    generated_at: IsoDate
    sections: list[ReportSection]

    @model_validator(mode="after")
    def _exactly_the_nineteen_sections(self) -> Self:
        numbers = [s.number for s in self.sections]
        if numbers != list(range(1, SECTION_COUNT + 1)):
            raise ValueError("a report has exactly the 19 blueprint sections, numbered 1..19 in order")
        return self
