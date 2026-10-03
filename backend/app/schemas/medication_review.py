"""medication_review.v1: the structured output of the Medication Safety capability.

It lives in `SpecialistReport.extensions["medication_review"]`, so the specialist-report contract, the trace
and the UI stay as they are. Medication review is a first-class capability: for every documented medicine it
records what the record does and does NOT say (purpose, dose, frequency, duration), and it surfaces concerns
and discussion points for a real doctor.

What it must never contain, by construction: an instruction to stop, start or change a medicine, a dose
recommendation, or a statement that a doctor is wrong. The contract has no field for any of those. Free text
is additionally gated by `app.safety.output_lint`. A concern needs evidence: from the patient's own record
(`fact_refs`) or from a registered external source (`source_ids`). Without either it is not a concern, it is
at most a discussion point.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .common import Id, NonEmpty, WireModel

MEDICATION_REVIEW_SCHEMA_VERSION = "medication_review.v1"

FieldStatus = Literal["documented", "not_documented", "unclear"]
ConcernKind = Literal[
    "possible_interaction",
    "possible_duplication",
    "dose_or_frequency_unclear",
    "purpose_not_documented",
    "duration_not_documented",
    "documented_conflict",
    "monitoring_not_documented",
    "other",
]
EvidenceBasis = Literal["patient_record", "external_reference"]


class DocumentedValue(WireModel):
    """What the record says about one aspect of a medicine. `value` only when it is documented."""

    status: FieldStatus
    value: str | None = None

    @model_validator(mode="after")
    def _value_only_when_documented(self) -> Self:
        if self.status == "documented" and not (self.value or "").strip():
            raise ValueError("a documented value needs its text")
        if self.status != "documented" and self.value is not None:
            raise ValueError("an undocumented or unclear value carries no text")
        return self


class MedicationEntry(WireModel):
    id: Id
    medication: NonEmpty
    fact_refs: Annotated[list[Id], Field(min_length=1)]
    purpose: DocumentedValue
    dose: DocumentedValue
    frequency: DocumentedValue
    duration: DocumentedValue


class MedicationConcern(WireModel):
    id: Id
    kind: ConcernKind
    statement: NonEmpty
    basis: EvidenceBasis
    medication_ids: Annotated[list[Id], Field(min_length=1)]
    fact_refs: list[Id]
    source_ids: list[Id]

    @model_validator(mode="after")
    def _a_concern_has_evidence_of_its_stated_basis(self) -> Self:
        if self.basis == "patient_record" and not self.fact_refs:
            raise ValueError("a patient_record concern cites at least one fact")
        if self.basis == "external_reference" and not self.source_ids:
            raise ValueError("an external_reference concern cites at least one registered source")
        return self


class DiscussionPoint(WireModel):
    """A question or topic for the treating or second-opinion doctor. Never an instruction."""

    id: Id
    text: NonEmpty
    linked_to: Annotated[list[Id], Field(min_length=1)]


class MedicationReview(WireModel):
    schema_version: Literal["medication_review.v1"]
    medicines: list[MedicationEntry]
    concerns: list[MedicationConcern]
    discussion_points: list[DiscussionPoint]
    missing_information: list[str]
    limitations: Annotated[list[str], Field(min_length=1)]
