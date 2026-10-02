"""specialist_report.v1: what one specialist agent returns for one run of one case."""

from typing import Any, Literal

from .common import Confidence, FactKind, Id, Importance, NonEmpty, Rank, SpecialistId, WireModel

SPECIALIST_REPORT_SCHEMA_VERSION = "specialist_report.v1"


class Finding(WireModel):
    id: Id
    statement: NonEmpty
    kind: FactKind
    importance: Importance
    fact_refs: list[Id]
    source_ids: list[Id] | None = None


class Uncertainty(WireModel):
    id: Id
    text: NonEmpty
    impact: Importance
    resolvable_by: str | None = None


class MissingInfo(WireModel):
    id: Id
    item: NonEmpty
    why_it_matters: str


class Contradiction(WireModel):
    id: Id
    description: str
    between: list[Id]


class SpecialistQuestion(WireModel):
    id: Id
    text: NonEmpty
    priority: Rank
    # Finding / uncertainty / missing-info IDs that triggered the question.
    linked_to: list[Id]


class EvidenceRef(WireModel):
    source_id: Id
    title: str
    section: str


class ConfidenceStatement(WireModel):
    overall: Confidence
    reason: str


class SpecialistReport(WireModel):
    schema_version: Literal["specialist_report.v1"]
    id: Id
    run_id: Id
    case_id: Id
    specialist: SpecialistId
    name: NonEmpty
    version: NonEmpty
    tier: Rank
    priority: Literal["mandatory", "optional"]
    routing_reason: str
    status: Literal["complete", "incomplete", "failed"]
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
    # Specialty-specific additions, e.g. {"cardiology": {"risk_scores_mentioned": []}}.
    extensions: dict[str, Any] | None = None
