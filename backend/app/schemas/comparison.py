"""Second-opinion comparison: two doctors' views side by side. Mirrors `ComparisonSchema`.

It shows what agrees, differs, is new or unresolved. It never picks a winner, scores a doctor or suggests
switching; the contract has no field for any of that."""

from typing import Literal

from .common import Id, WireModel
from .questions import QuestionStatus

ComparisonRelationship = Literal["agreement", "differs", "new_info", "changed", "unresolved"]


class ComparisonRow(WireModel):
    id: Id
    topic: str
    opinion_a: str
    opinion_b: str
    evidence_a: list[Id]
    evidence_b: list[Id]
    relationship: ComparisonRelationship
    item_ids: list[Id]


class NextQuestion(WireModel):
    audience: str
    text: str
    item_ids: list[Id]


class AnsweredByOpinion(WireModel):
    question_id: Id
    note: str
    status: QuestionStatus


class Comparison(WireModel):
    opinion_a_label: str
    opinion_b_label: str
    rows: list[ComparisonRow]
    next_questions: list[NextQuestion]
    answered_by_opinion: list[AnsweredByOpinion]


class SecondOpinionState(WireModel):
    status: Literal["none", "processing", "ready"]
    document_name: str | None = None
