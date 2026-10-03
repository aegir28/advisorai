"""Extension points for routing: deterministic rules and LLM-assisted proposals.

Neither ships with any rule or prompt. `RuleStrategy` runs the rules you give it; `LLMAssistedStrategy` is an
abstract base for a model-backed proposal that still passes through the router's registry filter, guardrails
and
cap, so a model can only ever propose among enabled, registered specialties."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from app.ai.gateway import AIGateway, GatewayRequest
from app.ai.types import CallContext
from app.router.contracts import Candidate, Priority, Proposal, RouterInput
from app.schemas.common import SpecialistId


@dataclass(frozen=True, slots=True)
class Rule:
    """One deterministic rule: when `when(input)` is true, propose `specialty` with `reason`."""

    specialty: SpecialistId
    priority: Priority
    reason: str
    when: Callable[[RouterInput], bool]


class RuleStrategy:
    def __init__(self, rules: Sequence[Rule], *, name: str = "rules") -> None:
        self.name = name
        self._rules = list(rules)

    async def propose(self, routing_input: RouterInput) -> Proposal:
        return Proposal(
            candidates=[
                Candidate(r.specialty, r.priority, r.reason, self.name)
                for r in self._rules
                if r.when(routing_input)
            ]
        )


class ProposedSelection(BaseModel):
    specialty: SpecialistId
    priority: Priority
    reason: str


class RoutingProposal(BaseModel):
    """The output schema an LLM-assisted strategy asks the gateway for."""

    selections: list[ProposedSelection]
    missing: list[str] = []


class LLMAssistedStrategy(ABC):
    """Subclass and implement `build_request` (prompt, tier, segments). The proposal is validated by the
    gateway
    against `RoutingProposal` before it becomes candidates."""

    name = "llm"

    def __init__(self, gateway: AIGateway) -> None:
        self._gateway = gateway

    @abstractmethod
    def build_request(self, routing_input: RouterInput) -> GatewayRequest[RoutingProposal]: ...

    async def propose(self, routing_input: RouterInput) -> Proposal:
        request = self.build_request(routing_input)
        request.context = request.context or CallContext()
        request.context.purpose = "router.propose"
        result = await self._gateway.invoke(request)
        return Proposal(
            candidates=[
                Candidate(s.specialty, s.priority, s.reason, self.name) for s in result.output.selections
            ],
            missing=result.output.missing,
        )
