"""Evidence and verification: claims an agent made, how each was checked, and the sources behind them.

Mirrors `ClaimSchema` / `EvidenceDataSchema` in frontend/src/domain/schemas.ts. A claim is verified against
the patient's own facts (`patient_fact_ids`) and against curated external sources (`external_source_ids`); a
claim that cannot be traced is kept with `removed=True` and a reason, so people see what was filtered out.
"""

from .common import ExternalSource, FactKind, Id, NonEmpty, SpecialistId, VerificationStatus, WireModel


class Claim(WireModel):
    id: Id
    text: NonEmpty
    kind: FactKind
    agent: SpecialistId
    status: VerificationStatus
    rationale: str
    patient_fact_ids: list[Id]
    external_source_ids: list[Id]
    removed: bool | None = None
    removal_reason: str | None = None


class EvidenceData(WireModel):
    claims: list[Claim]
    sources: list[ExternalSource]
