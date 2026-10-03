"""Cross-review: how the specialists' views relate topic by topic. Mirrors `CrossReviewDataSchema`."""

from typing import Literal

from .common import Id, SpecialistId, WireModel

CellStance = Literal["supports", "needs_context", "differs", "flags_issue", "not_assessed"]
MatrixRelationship = Literal[
    "agreement", "partial", "disagreement", "missing_info", "medication_conflict", "additional_context"
]


class MatrixPerspective(WireModel):
    specialist: SpecialistId
    reasoning: str


class MatrixRow(WireModel):
    id: Id
    topic: str
    cells: dict[SpecialistId, CellStance]
    relationship: MatrixRelationship
    summary: str
    perspectives: list[MatrixPerspective]
    item_ids: list[Id]


class MatrixSpecialist(WireModel):
    id: SpecialistId
    name: str


class CrossReviewData(WireModel):
    specialists: list[MatrixSpecialist]
    rows: list[MatrixRow]
