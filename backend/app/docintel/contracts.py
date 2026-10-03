"""Document-intelligence contracts: what text extraction, classification and fact extraction hand each other.

Contracts and deterministic checks only. Nothing here reads a model or decides what a document means. A future
extractor (local text layer, OCR, a vision model behind the AI gateway) returns these types; the provenance
check below is how the rest of the system refuses a "fact" that cannot be traced to the page it claims.

Evidence always uses `SourceRef` (doc_id, page, snippet), the same shape the patient-facing trace uses, so a
fact extracted here can be followed from the report down to a page without translation.
"""

import re
from typing import Annotated, Literal, Protocol

from pydantic import Field

from app.schemas.common import Confidence, Id, NonEmpty, PageNumber, SourceRef, WireModel

# Mirrors DocumentTypeSchema in frontend/src/domain/schemas.ts.
DocumentType = Literal["lab", "ecg", "prescription", "discharge", "imaging", "consult", "other"]
# What a fact is about. Extend with a migration of the `facts` table when a new category is needed.
FactCategory = Literal[
    "symptom",
    "diagnosis",
    "medication",
    "lab_result",
    "imaging_finding",
    "procedure",
    "history",
    "allergy",
    "recommendation",
]
EntityType = Literal["condition", "medication", "lab_test", "procedure", "anatomy", "measurement"]
TextLayer = Literal["full", "partial", "none"]


class PageText(WireModel):
    page: PageNumber
    text: str
    # False for an image-only page: there is nothing to read without OCR (not implemented).
    has_text_layer: bool


class DocumentText(WireModel):
    doc_id: Id
    pages: list[PageText]
    extractor: NonEmpty  # which implementation produced it, e.g. "pypdf-text-layer"

    def page_text(self, page: int) -> str | None:
        return next((p.text for p in self.pages if p.page == page), None)

    @property
    def text_layer(self) -> TextLayer:
        with_text = sum(1 for p in self.pages if p.has_text_layer)
        if not self.pages or with_text == 0:
            return "none"
        return "full" if with_text == len(self.pages) else "partial"


class DocumentMetadata(WireModel):
    """Technical facts about a document: page count, size, hash, how much of it is machine-readable."""

    doc_id: Id
    mime_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size_bytes: Annotated[int, Field(ge=0)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    page_count: PageNumber
    text_layer: TextLayer
    # True when some page has no text layer. OCR is NOT implemented; this only says the gap exists.
    needs_ocr: bool


class DocumentClassification(WireModel):
    doc_id: Id
    document_type: DocumentType
    confidence: Confidence
    # Where in the document the type was recognised (not required: a classifier may use the whole file).
    evidence: list[SourceRef]


class EntityMention(WireModel):
    type: EntityType
    text: NonEmpty
    # Optional normalised form (for example a standard code). Never invented by the contract.
    normalized: str | None = None


class ExtractedFact(WireModel):
    id: Id
    doc_id: Id
    category: FactCategory
    text: NonEmpty
    # Optional structured value for measurements: kept as text so units and ranges are never reinterpreted.
    value: str | None = None
    unit: str | None = None
    # Date the fact is about (not the upload date), as written in the document.
    date: str | None = None
    entities: list[EntityMention]
    confidence: Confidence
    source: SourceRef


class ExtractionBatch(WireModel):
    doc_id: Id
    facts: list[ExtractedFact]


# ── interfaces (implemented by whoever builds the extractor) ───────────────────────────────────────
class TextExtractor(Protocol):
    async def extract(self, data: bytes, mime_type: str, doc_id: str) -> DocumentText: ...


class DocumentClassifier(Protocol):
    async def classify(self, document: DocumentText) -> DocumentClassification: ...


class FactExtractor(Protocol):
    async def extract(
        self, document: DocumentText, classification: DocumentClassification
    ) -> ExtractionBatch: ...


# ── provenance: a deterministic check, not a model ─────────────────────────────────────────────────
Provenance = Literal["verified", "wrong_document", "page_missing", "snippet_not_found"]
_SPACE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACE.sub(" ", text).strip().casefold()


class ProvenanceReport(WireModel):
    verdicts: dict[str, Provenance]  # fact id -> verdict

    @property
    def unverified_ids(self) -> list[str]:
        return sorted(i for i, v in self.verdicts.items() if v != "verified")

    @property
    def all_verified(self) -> bool:
        return not self.unverified_ids


def verify_provenance(batch: ExtractionBatch, document: DocumentText) -> ProvenanceReport:
    """Every fact must cite a page of THIS document and a snippet that really appears on that page
    (whitespace- and case-insensitive). A fact that fails is not trustworthy and must not reach the case."""
    verdicts: dict[str, Provenance] = {}
    for fact in batch.facts:
        if fact.doc_id != document.doc_id or fact.source.doc_id != document.doc_id:
            verdicts[fact.id] = "wrong_document"
            continue
        page = document.page_text(fact.source.page)
        if page is None:
            verdicts[fact.id] = "page_missing"
        elif _norm(fact.source.snippet) not in _norm(page):
            verdicts[fact.id] = "snippet_not_found"
        else:
            verdicts[fact.id] = "verified"
    return ProvenanceReport(verdicts=verdicts)


def drop_unverified(batch: ExtractionBatch, report: ProvenanceReport) -> ExtractionBatch:
    """The batch without facts that failed provenance, in original order."""
    return ExtractionBatch(
        doc_id=batch.doc_id, facts=[f for f in batch.facts if report.verdicts.get(f.id) == "verified"]
    )
