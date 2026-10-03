"""What a specialty agent is, what it receives and what it must return.

* Input: `SpecialtyInput` = the de-identified structured case (`case.v1`, which by contract carries no
  identity) plus why this agent was chosen, plus optional evidence it may cite.
* Output: the existing `specialist_report.v1` (`SpecialistReport`): findings, uncertainties, missing
  information, contradictions, confidence, limitations, evidence references. Reusing it keeps the UI, the
  trace and the contract tests on one definition.
* Metadata: `AgentSpec`, loaded from `registry/agents.yaml`.
"""

from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints

from app.ai.types import CallContext
from app.schemas.case import CaseV1
from app.schemas.common import ExternalSource, Id, NonEmpty, Rank, SpecialistId, WireModel
from app.schemas.routing import RoutingSelection
from app.schemas.specialist_report import SpecialistReport

SPECIALTY_INPUT_SCHEMA_VERSION = "specialty_input.v1"

# The MVP starter set: the specialists the first end-to-end run needs. It is a STARTING POINT, not a ceiling
# (ADR 0012): the registry holds any number of specialties and sub-specialties, and a new one is a registry
# entry, never a change to the workflow.
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


AgentKind = Literal["specialty", "subspecialty", "capability"]
PromptMode = Literal["shared", "file"]
TriggerPriority = Literal["mandatory", "optional"]


class Trigger(WireModel):
    """Configuration, not code: "select this agent when this case signal is present"."""

    signal: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,47}$")]
    priority: TriggerPriority
    # Fixed text. It must never contain case content; the router adds only counts of what matched.
    reason: NonEmpty


class AgentSpec(WireModel):
    id: SpecialistId
    name: NonEmpty
    version: NonEmpty
    tier: Rank
    prompt_version: Annotated[int, Field(ge=1)]
    timeout_s: Annotated[int, Field(ge=5, le=600)]
    enabled: bool
    # ── registry v2: what makes a specialist data, not code ───────────────────────────────────────
    # specialty = a medical area; subspecialty = narrower, has a `parent`; capability = a cross-cutting review
    # (for example medication safety) that is not a medical specialty.
    kind: AgentKind = "specialty"
    parent: SpecialistId | None = None
    # One neutral sentence on what this perspective looks at; inserted into the shared specialist prompt.
    focus: str = ""
    # `shared`: the shared specialist base prompt + `focus` (a new specialist needs no prompt file).
    # `file`: a dedicated prompt file prompts/<id>/v<prompt_version>.md (refused while it is a placeholder).
    prompt_mode: PromptMode = "file"
    max_output_tokens: Annotated[int, Field(ge=256, le=8192)] = 2048
    # Agent-specific spend ceiling per call, in micro-USD. 0 = no extra ceiling beyond the run budget.
    max_call_cost_micro_usd: Annotated[int, Field(ge=0)] = 0
    # Names of optional tools this agent may use (none exist yet; the field fixes the extension point).
    tools: list[str] = Field(default_factory=list)
    triggers: list[Trigger] = Field(default_factory=list)
    # Output contract identifiers, so a registry entry says exactly what it promises to return.
    input_schema: Literal["specialty_input.v1"] = "specialty_input.v1"
    output_schema: Literal["specialist_report.v1"] = "specialist_report.v1"


class SpecialtyAgent(Protocol):
    """Implemented per specialty by whoever writes the agent. `run` returns a report that has passed (or will
    be
    passed through) `validate_specialist_report`; it must never return anything but a `SpecialistReport`."""

    spec: AgentSpec

    async def run(self, payload: SpecialtyInput, context: CallContext) -> SpecialistReport: ...
