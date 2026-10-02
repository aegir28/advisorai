"""Wire contracts for the case and document endpoints (the `AdvisorApi` surface in the frontend).

These are request/response models, not versioned agent contracts: `case.v1` stays the canonical structured
case the pipeline will fill in later. Identity never appears here: a case is shown by its pseudonymous
`code`, and the owner is never a field (the owner is always the verified caller).

Optional means ABSENT on the wire, never null (ADR 0001).
"""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from .common import Id, Sex, WireModel

CaseStatus = Literal["draft", "awaiting_upload", "processing", "complete", "partial", "failed"]
DocumentType = Literal["lab", "ecg", "prescription", "discharge", "imaging", "consult", "other"]
# `pending_upload` is internal and never leaves the backend (ADR 0004).
DocumentStatus = Literal["ready", "processing", "needs_attention", "duplicate"]
RedFlagCategory = Literal["cardiac", "stroke", "breathing", "bleeding", "self_harm"]

ALLOWED_MIME_TYPES = ("application/pdf", "image/jpeg", "image/png")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

Concern = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Intent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Treatment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class CaseSummary(WireModel):
    id: Id
    code: Id
    age_years: Annotated[int, Field(ge=0, le=120)]
    sex: Sex
    concern: str
    proposed_treatment: str | None = None
    status: CaseStatus
    document_count: Annotated[int, Field(ge=0)]
    updated_at: str
    run_id: Id | None = None
    title: str | None = None


class NewCaseInput(WireModel):
    intent: Intent | None = None
    concern: Concern
    proposed_treatment: Treatment | None = None
    age_years: Annotated[int, Field(ge=0, le=120)]
    sex: Sex


class DocumentItem(WireModel):
    id: Id
    name: str
    type: DocumentType
    pages: Annotated[int, Field(ge=1)] | None = None
    size_kb: Annotated[float, Field(ge=0)]
    status: DocumentStatus
    uploaded_at: str
    ocr_confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    note: str | None = None


class UploadUrlRequest(WireModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    type: DocumentType = "other"
    mime_type: Literal["application/pdf", "image/jpeg", "image/png"]
    size_bytes: Annotated[int, Field(ge=1, le=MAX_UPLOAD_BYTES)]


class UploadUrlResponse(WireModel):
    document_id: Id
    # A short-lived capability URL. The client PUTs the file to it; it is never logged or audited.
    upload_url: str
    expires_in: Annotated[int, Field(ge=1)]


class SafetyCheckRequest(WireModel):
    text: Annotated[str, StringConstraints(max_length=8000)]
    # Symptoms the person ticked as happening right now.
    current_symptoms: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)


class SafetyCheckResult(WireModel):
    red_flag: bool
    matched: list[str]
    category: RedFlagCategory | None = None
