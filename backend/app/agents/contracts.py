"""What a specialty agent is, what it receives and what it must return.

* Input: `SpecialtyInput` = the de-identified structured case (`case.v1`, which by contract carries no
  identity) plus why this agent was chosen, plus optional evidence it may cite.
* Output: the existing `specialist_report.v1` (`SpecialistReport`): findings, uncertainties, missing
  information, contradictions, confidence, limitations, evidence references. Reusing it keeps the UI, the
  trace and the contract tests on one definition.
* Metadata: `AgentSpec`, loaded from `registry/agents.yaml`.
"""

from typing import Annotated, Literal, Protocol

from pydantic import Field

from app.ai.types import CallContext
from app.schemas.case import CaseV1
from app.schemas.common import ExternalSource, Id, NonEmpty, Rank, SpecialistId, WireModel
from app.schemas.routing import RoutingSelection
from app.schemas.specialist_report import SpecialistReport

SPECIALTY_INPUT_SCHEMA_VERSION = "specialty_input.v1"

# The five specialties of this delivery. (`interventional_cardiology` exists in the UI contract and can be
# added
# to the registry the same way.)
REQUIRED_SPECIALTIES: tuple[SpecialistId, ...] = (
    "general_medicine",
    "cardiology",
    "orthopedics",
    "neurology",
    "medication_safety",
)


class SpecialtyInput(WireModel):
    schema_version: Literal["specialty_input.v1"]
    run_id: Id
    case: CaseV1
    # Why this specialist was selected (from the router): the agent may state it but must not redefine it.
    routing: RoutingSelection
    # Curated external references it is allowed to cite. Empty means "no external evidence available".
    sources: list[ExternalSource]


class AgentSpec(WireModel):
    id: SpecialistId
    name: NonEmpty
    version: NonEmpty
    tier: Rank
    prompt_version: Annotated[int, Field(ge=1)]
    timeout_s: Annotated[int, Field(ge=5, le=600)]
    enabled: bool
    # Output contract identifiers, so a registry entry says exactly what it promises to return.
    input_schema: Literal["specialty_input.v1"] = "specialty_input.v1"
    output_schema: Literal["specialist_report.v1"] = "specialist_report.v1"


class SpecialtyAgent(Protocol):
    """Implemented per specialty by whoever writes the agent. `run` returns a report that has passed (or will
    be
    passed through) `validate_specialist_report`; it must never return anything but a `SpecialistReport`."""

    spec: AgentSpec

    async def run(self, payload: SpecialtyInput, context: CallContext) -> SpecialistReport: ...
