"""Evidence contracts.

An `EvidenceItem` is one citable thing: a passage of the patient's own document (`SourceRef`, the same shape
the
trace uses) or a passage of a curated external reference (`ExternalSource`). Exactly one of the two is set, so
"where did this come from" always has a single, concrete answer.
"""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from app.schemas.common import ExternalSource, Id, NonEmpty, SourceRef, VerificationStatus, WireModel

EvidenceOrigin = Literal["patient_document", "external_reference"]


class EvidenceItem(WireModel):
    id: Id
    origin: EvidenceOrigin
    patient_source: SourceRef | None = None
    external_source: ExternalSource | None = None

    @model_validator(mode="after")
    def _exactly_one_source_matching_origin(self) -> Self:
        if self.origin == "patient_document":
            if self.patient_source is None or self.external_source is not None:
                raise ValueError("a patient_document item carries exactly a patient_source")
        elif self.external_source is None or self.patient_source is not None:
            raise ValueError("an external_reference item carries exactly an external_source")
        return self

    @property
    def snippet(self) -> str:
        source = self.patient_source or self.external_source
        assert source is not None
        return source.snippet


class RetrievalQuery(WireModel):
    text: NonEmpty
    k: Annotated[int, Field(ge=1, le=50)] = 5
    origin: EvidenceOrigin | None = None


class RetrievedEvidence(WireModel):
    item: EvidenceItem
    # Higher is better. Meaning is defined by the retriever; only the order is part of the contract.
    score: float
    rank: Annotated[int, Field(ge=1)]


class EvidenceRetriever(Protocol):
    """Implemented later (embeddings + a vector store, or anything else). Must return at most `query.k` items,
    best first, ranks 1..n."""

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedEvidence]: ...


class VerificationResult(WireModel):
    claim_id: Id
    status: VerificationStatus
    patient_fact_ids: list[Id]
    external_source_ids: list[Id]
    rationale: str


class ClaimVerifier(Protocol):
    """Implemented later (rules, a model behind the gateway, or both). Returns one result per claim."""

    async def verify(
        self, claim_id: str, claim_text: str, items: list[EvidenceItem]
    ) -> VerificationResult: ...
