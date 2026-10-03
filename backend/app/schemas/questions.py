"""Personalised questions for the patient's visit. Mirrors `QuestionSchema`.

`trigger` says why the question exists for THIS person; `linked_item_ids` (at least one) connect it to the
findings, gaps or uncertainties that caused it, so a question is always traceable."""

from typing import Annotated, Literal

from pydantic import Field

from .common import Id, NonEmpty, Rank, WireModel
from .report import QuestionAudience

QuestionStatus = Literal["not_asked", "partially_answered", "answered"]


class Question(WireModel):
    id: Id
    audience: QuestionAudience
    priority: Rank
    category: str
    text: NonEmpty
    trigger: str
    linked_item_ids: Annotated[list[Id], Field(min_length=1)]
    status: QuestionStatus
    note: str | None = None
