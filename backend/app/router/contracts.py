"""Router contracts: what goes in, what a strategy proposes, what comes out."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel

from app.schemas.case import CaseV1
from app.schemas.common import SpecialistId
from app.schemas.routing import RoutingPlan

Priority = Literal["mandatory", "optional"]


class RouterInput(BaseModel):
    """What the router sees: the de-identified structured case. Strategies may read anything on it."""

    case: CaseV1


@dataclass(frozen=True, slots=True)
class Candidate:
    specialty: SpecialistId
    priority: Priority
    reason: str
    proposed_by: str  # the strategy's name


@dataclass(frozen=True, slots=True)
class Proposal:
    """One strategy's output: who it would select, and what it could not decide for lack of information."""

    candidates: Sequence[Candidate] = ()
    missing: Sequence[str] = ()


class RoutingStrategy(Protocol):
    name: str

    async def propose(self, routing_input: RouterInput) -> Proposal: ...


@dataclass(frozen=True, slots=True)
class GuardrailOutcome:
    candidates: Sequence[Candidate]
    # Human-readable, fixed-text notes about what was removed or changed and why.
    notes: Sequence[str] = ()


class Guardrail(Protocol):
    name: str

    def apply(self, candidates: Sequence[Candidate], routing_input: RouterInput) -> GuardrailOutcome: ...


class RoutingError(Exception):
    """Fixed code: too_many_mandatory, strategy_failed."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    plan: RoutingPlan
    # Ordered, content-free log of what each stage did (strategy names, guardrail notes, caps applied).
    trace: list[str] = field(default_factory=list)
