"""Structured synthesis: the combined view the patient report is written from. Mirrors `SynthesisSchema`.

The reviewer is an AI, never a human doctor, and the contract says so: `reviewer.label` is shown with the
content. Every item names the findings it was `derived_from`, so nothing in a synthesis is unsourced."""

from typing import Annotated, Literal

from pydantic import Field

from .common import Confidence, FactKind, Flag, Id, Importance, NonEmpty, WireModel

SynthesisGroup = Literal[
    "fact",
    "interpretation",
    "agreement",
    "disagreement",
    "missing",
    "uncertainty",
    "clarification",
    "medication",
    "proposal",
]


class SynthesisItem(WireModel):
    id: Id
    text: NonEmpty
    kind: FactKind
    group: SynthesisGroup
    confidence: Confidence
    flag: Flag | None = None
    derived_from: Annotated[list[Id], Field(min_length=1)]
    impact: Importance | None = None


class SynthesisReviewer(WireModel):
    label: str
    tier: Literal[2, 3]
    escalated: bool
    escalation_reason: str | None = None


class RubricRow(WireModel):
    factor: str
    weight: str


class Synthesis(WireModel):
    id: Id
    reviewer: SynthesisReviewer
    items: list[SynthesisItem]
    rubric: list[RubricRow]
