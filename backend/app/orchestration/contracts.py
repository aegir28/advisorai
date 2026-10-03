"""Contracts of the orchestration layer: the n8n <-> backend API, the artifacts, and the model-output schemas.

Three groups:

* API (`orchestration_start.v1`, `stage_result.v1`, ...): what crosses between the backend and n8n. By
  design it carries ids, statuses and counts only. n8n never receives case content, a prompt or a model
  answer.
* Artifacts (`case_context.v1`, ...): what each stage stores in `analysis_artifacts` for later stages and for
  the owner. They may hold document text and model output; they never leave the backend except to the owner.
* Model outputs (`*ModelOutput`): the narrow schemas the AI gateway asks models for. They are deliberately
  smaller than the final contracts: the backend stamps ids, versions and routing, so a model cannot forge
  them, and the backend decides what is kept (a removed claim stays removed whatever a model says).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evidence.contracts import EvidenceItem
from app.schemas.case import CaseV1
from app.schemas.common import (
    Confidence,
    FactKind,
    Flag,
    Id,
    Importance,
    IsoDate,
    NonEmpty,
    Rank,
    SpecialistId,
    VerificationStatus,
    WireModel,
)
from app.schemas.evidence import Claim
from app.schemas.report import QuestionAudience
from app.schemas.routing import RoutingPlan
from app.schemas.specialist_report import (
    ConfidenceStatement,
    Contradiction,
    EvidenceRef,
    Finding,
    MissingInfo,
    SpecialistQuestion,
    SpecialistReport,
    Uncertainty,
)
from app.schemas.synthesis import Synthesis, SynthesisGroup

# ═══ API: backend <-> n8n (ids, statuses, counts only) ═══════════════════════════════════════════
StageStatus = Literal["ok", "skipped", "unavailable", "failed", "cancelled"]


class OrchestrationStart(WireModel):
    """Backend -> n8n master webhook. No owner, no content: n8n calls back with the run id."""

    schema_version: Literal["orchestration_start.v1"]
    run_id: Id
    case_id: Id
    workflow: Literal["case_analysis", "second_opinion"]
    resume: bool


class StageResult(WireModel):
    schema_version: Literal["stage_result.v1"]
    run_id: Id
    stage: Id
    status: StageStatus
    # True when this stage had already run (idempotent retry or resume): nothing was recomputed or re-billed.
    cached: bool
    code: str | None = None
    # True when n8n may retry this stage (a transient provider/storage failure), False when a retry cannot help.
    retryable: bool
    counts: dict[str, int]
    # Branch conditions decided by the backend from registry/orchestration.yaml, e.g. extra_verification.
    flags: dict[str, bool]


class PlannedAgent(WireModel):
    id: SpecialistId
    priority: Literal["mandatory", "optional"]
    timeout_s: int


class RunPlan(WireModel):
    schema_version: Literal["run_plan.v1"]
    run_id: Id
    agents: list[PlannedAgent]
    max_parallel: int
    extra_verification: bool
    missing_info_branch: bool


class AgentResult(WireModel):
    schema_version: Literal["agent_result.v1"]
    run_id: Id
    agent_id: SpecialistId
    status: Literal["ok", "unavailable", "failed", "cancelled"]
    cached: bool
    code: str | None = None


class BeginResult(WireModel):
    schema_version: Literal["begin_result.v1"]
    run_id: Id
    workflow: Literal["case_analysis", "second_opinion"]
    stages: list[Id]
    completed_stages: list[Id]
    stage_retries: int
    backoff_seconds: int
    stage_timeout_seconds: int
    agent_timeout_seconds: int
    max_parallel_agents: int


class FinishResult(WireModel):
    schema_version: Literal["finish_result.v1"]
    run_id: Id
    status: Literal["complete", "partial", "failed"]


# ═══ Artifacts ═══════════════════════════════════════════════════════════════════════════════════════
class DocumentBrief(WireModel):
    doc_id: Id
    type: str
    pages: Annotated[int, Field(ge=0)]
    text_layer: Literal["full", "partial", "none"]


class TimelineEntry(WireModel):
    id: Id
    date: IsoDate
    title: NonEmpty
    fact_id: Id


class CaseContext(WireModel):
    """The structured, de-identified case every relevant specialist receives, with its evidence index."""

    schema_version: Literal["case_context.v1"]
    case: CaseV1
    evidence_index: list[EvidenceItem]
    documents: list[DocumentBrief]
    timeline: list[TimelineEntry]
    # Counts of documents that could not be read (no text layer, not OCR'd): said out loud, never hidden.
    unreadable_documents: Annotated[int, Field(ge=0)]


class RoutingArtifact(WireModel):
    schema_version: Literal["routing_plan.v1"]
    plan: RoutingPlan
    trace: list[str]
    agent_tiers: dict[str, Rank]


class SpecialistArtifact(WireModel):
    """One specialist's outcome. `report` is present only for a usable result; an unavailable specialist is
    recorded as such with a reason code, never as an invented report."""

    schema_version: Literal["specialist_artifact.v1"]
    agent_id: SpecialistId
    status: Literal["ok", "unavailable", "failed"]
    reason_code: str | None = None
    report: SpecialistReport | None = None


class VerificationArtifact(WireModel):
    schema_version: Literal["verification.v1"]
    claims: list[Claim]
    # status -> count
    counts: dict[str, int]
    mode: Literal["standard", "deep"]


class RunSummary(WireModel):
    """Run-level facts the final report states honestly: who was available, what was missing."""

    schema_version: Literal["run_summary.v1"]
    agents_ok: list[SpecialistId]
    agents_unavailable: list[SpecialistId]
    unreadable_documents: int
    missing_info_branch: bool
    removed_claims: int


# ═══ Model-output schemas (what the gateway asks a model for) ═════════════════════════════════════
def _strip_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_nulls(v) for v in value]
    return value


class ModelOutput(BaseModel):
    """Top level of anything a MODEL returns. Providers' strict JSON modes emit `null` for an optional field;
    the wire contracts mean "absent", so nulls are dropped (recursively) before validation. Everything else
    stays strict: unknown keys, wrong types and bad values are still rejected. (Deliberately not a
    `WireModel`: it is never a wire contract, only the shape a model is asked to return.)"""

    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        return _strip_nulls(data)


class ModelFact(WireModel):
    category: Literal[
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
    text: NonEmpty
    value: str | None = None
    unit: str | None = None
    date: str | None = None
    confidence: Confidence
    page: Annotated[int, Field(ge=1)]
    # A short quote copied from the page. The backend checks it really appears on that page.
    snippet: NonEmpty


class FactsModelOutput(ModelOutput):
    facts: list[ModelFact]


class SpecialistModelOutput(ModelOutput):
    """What a specialist model returns. The backend adds identity, version, tier, priority and routing."""

    status: Literal["complete", "incomplete"]
    status_note: str | None = None
    confidence: ConfidenceStatement
    findings: list[Finding]
    uncertainties: list[Uncertainty]
    missing_info: list[MissingInfo]
    contradictions: list[Contradiction]
    considerations: list[Finding]
    questions: list[SpecialistQuestion]
    evidence_refs: list[EvidenceRef]
    limitations: list[str]
    # For capability agents with a structured extension (medication_safety -> medication_review.v1).
    medication_review: dict[str, object] | None = None


class VerificationModelResult(WireModel):
    claim_id: Id
    status: VerificationStatus
    rationale: NonEmpty


class VerificationModelOutput(ModelOutput):
    results: list[VerificationModelResult]


class ReviewItem(WireModel):
    text: NonEmpty
    kind: FactKind
    group: SynthesisGroup
    confidence: Confidence
    flag: Flag | None = None
    # Claim ids, finding ids or fact refs this item rests on. Never empty: no unsourced synthesis item.
    derived_from: Annotated[list[Id], Field(min_length=1)]
    impact: Importance | None = None
    # Optional placement hint: which report section (1..18) this item belongs in.
    section: Annotated[int, Field(ge=1, le=18)] | None = None


class ReviewModelOutput(ModelOutput):
    items: list[ReviewItem]


class ModelQuestion(WireModel):
    audience: QuestionAudience
    priority: Rank
    category: NonEmpty
    text: NonEmpty
    trigger_kind: Literal[
        "patient_question",
        "missing_information",
        "uncertainty",
        "disagreement",
        "evidence_gap",
        "medication",
        "treatment",
        "unresolved",
    ]
    linked_item_ids: Annotated[list[Id], Field(min_length=1)]


class QuestionsModelOutput(ModelOutput):
    questions: list[ModelQuestion]


class SimplifiedItem(WireModel):
    id: Id
    text: NonEmpty


class SimplifiedModelOutput(ModelOutput):
    items: list[SimplifiedItem]


class ModelComparisonRow(WireModel):
    topic: NonEmpty
    opinion_a: NonEmpty
    opinion_b: NonEmpty
    evidence_a: list[Id]
    evidence_b: list[Id]
    relationship: Literal["agreement", "differs", "new_info", "changed", "unresolved"]
    item_ids: Annotated[list[Id], Field(min_length=1)]


class ComparisonModelOutput(ModelOutput):
    rows: list[ModelComparisonRow]
    next_questions: list[ModelQuestion]


class SynthesisArtifact(WireModel):
    schema_version: Literal["synthesis_artifact.v1"]
    synthesis: Synthesis
    # synthesis item id -> report section (1..18) the reviewer proposed (validated against the item's group)
    section_hints: dict[str, int]
    # "model" when the reviewer model produced it, "fallback" when it was assembled from verified claims alone.
    produced_by: Literal["model", "fallback"]
    # reason code -> how many reviewer items were dropped (never the text).
    dropped: dict[str, int]
