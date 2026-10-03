"""Generic AI step for the workflow engine: the boundary between a workflow node and the AI gateway.

This file adds NO clinical behaviour and NO topology. It is the plumbing a future AI node plugs into:

* a node describes its call (`build_request`) and what to do with the validated output (`handle_output`);
* `run` invokes the gateway with full correlation (run, case, owner, node, request id), so every call lands in
  `model_usage` against the right step;
* gateway failures become the engine's own error types, so retry / critical / partial handling is unchanged:
  retryable provider trouble -> `RetryableError` (the engine retries the step); everything else -> `NodeError`
  with a short code and a fixed, person-safe note. Exception text and model output never reach the step row.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.ai.gateway import AIGateway, GatewayRequest, GatewayResult
from app.ai.types import CallContext, GatewayError
from app.workflow.engine import NodeError, RetryableError, RunContext, StepResult

# Fixed, person-safe notes shown in the progress UI. Keyed by gateway error code.
_NOTES: dict[str, str] = {
    "pii_blocked": "This step was skipped to protect your privacy.",
    "budget_exceeded": "This step was skipped because the review reached its limit.",
    "model_not_configured": "This step is not available right now.",
    "schema_validation_failed": "This step could not produce a reliable result.",
    "retries_exhausted": "This step could not be completed. Please try again.",
}
_DEFAULT_NOTE = "This step could not be completed."


def to_node_error(error: GatewayError) -> NodeError:
    note = _NOTES.get(error.code, _DEFAULT_NOTE)
    if error.retryable:
        return RetryableError(error.code, note=note)
    return NodeError(error.code, note=note)


class AINode[T: BaseModel](ABC):
    """Subclass per AI step. Register an instance under a node type in `app/workflow/nodes.py`."""

    #: Short machine name used in usage rows and audit, e.g. "docintel.classify". Lowercase, dots/underscores.
    purpose: str = "ai.step"

    def __init__(self, gateway: AIGateway) -> None:
        self._gateway = gateway

    @abstractmethod
    async def build_request(self, ctx: RunContext) -> GatewayRequest[T]:
        """Describe the call: output schema, system prompt, segments (free text is de-identified), tier."""

    @abstractmethod
    async def handle_output(self, ctx: RunContext, result: GatewayResult[T]) -> StepResult:
        """Persist/use the VALIDATED output. Return the step outcome (done / warning / skipped)."""

    def fingerprint_extra(self, ctx: RunContext) -> str:
        """Anything else that should force a re-run when it changes (for example a prompt version)."""
        return ""

    def input_fingerprint(self, ctx: RunContext) -> str:
        # The provider is part of the fingerprint: switching fake -> openai must not reuse fake results.
        return f"{self.purpose}|{self._gateway.provider_name}|{self.fingerprint_extra(ctx)}"

    async def run(self, ctx: RunContext) -> StepResult:
        request = await self.build_request(ctx)
        request.context = CallContext(
            run_id=str(ctx.run_id),
            case_id=str(ctx.case_id),
            owner_user_id=str(ctx.owner_user_id),
            node_id=ctx.node_id or None,
            purpose=self.purpose,
        )
        try:
            result = await self._gateway.invoke(request)
        except GatewayError as exc:
            raise to_node_error(exc) from None
        return await self.handle_output(ctx, result)
