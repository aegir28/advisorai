"""A small, explicit workflow engine (blueprint p. 46): DAG layers run in parallel, every step is persisted,
a restart resumes instead of redoing, and a failure is never silent.

* Nodes implement `run(ctx) -> StepResult`. Which node implements a TYPE is the `NodeRegistry`'s business;
  this phase registers none (there is no AI yet), so the engine is exercised with test nodes only.
* Idempotent: a node's inputs are hashed. If a step with the same hash already succeeded for the case it is
  reused; a resumed run skips steps that are already done.
* Retries (max 2, exponential backoff) apply to `RetryableError` and timeouts. Anything else fails at once.
  A critical node that fails stops the run (`failed`); a non-critical one makes it `partial`.
* Never silent: every failure leaves a step error code and, for a failed run, a person-safe explanation.
  Exception text from a node is never stored or logged (it could contain document content); only its type.
"""

import asyncio
import dataclasses
import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from app.audit.writer import AuditAction, AuditWriter
from app.workflow.definitions import DefinitionRegistry, NodeSpec
from app.workflow.repository import ClaimedRun, StepRow, WorkflowRepository

logger = logging.getLogger("advisorai.workflow")

DEFAULT_FAILURE_TITLE = "We couldn't finish reading your records"
DEFAULT_FAILURE_BODY = (
    "Something went wrong while preparing your case, so we stopped rather than guess. Please try again."
)
DEFAULT_STEP_NOTE = "This step could not be completed."
_FINISHED = {"done", "warning", "skipped"}


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: uuid.UUID
    case_id: uuid.UUID
    owner_user_id: uuid.UUID
    definition_id: str
    definition_version: int
    # The id of the node being run (set by the engine per node). Used to correlate AI usage with a step.
    node_id: str = ""


@dataclass(frozen=True, slots=True)
class StepResult:
    status: Literal["done", "warning", "skipped"] = "done"
    # Fixed, person-safe text only (shown in the progress UI). Never document content.
    note: str | None = None


class NodeError(Exception):
    """Base for failures a node reports deliberately. `code` is a short machine code, e.g. `ocr_empty`."""

    def __init__(
        self, code: str, *, title: str | None = None, body: str | None = None, note: str | None = None
    ):
        super().__init__(code)
        self.code, self.title, self.body, self.note = code, title, body, note


class RetryableError(NodeError):
    """Worth another attempt (provider outage, rate limit). The engine retries up to the node's limit."""


class Node(Protocol):
    async def run(self, ctx: RunContext) -> StepResult: ...


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}

    def register(self, node_type: str, node: Node) -> None:
        if node_type in self._nodes:
            raise ValueError(f"node type {node_type!r} is already registered")
        self._nodes[node_type] = node

    def get(self, node_type: str) -> Node | None:
        return self._nodes.get(node_type)


class LeaseLostError(Exception):
    """Another worker owns the run now; this one must stop and write nothing more."""


def input_hash(ctx: RunContext, spec: NodeSpec, fingerprint: str) -> str:
    material = "|".join(
        [ctx.definition_id, str(ctx.definition_version), spec.id, spec.type, str(ctx.case_id), fingerprint]
    )
    return hashlib.sha256(material.encode()).hexdigest()


class Engine:
    def __init__(
        self,
        repository: WorkflowRepository,
        definitions: DefinitionRegistry,
        registry: NodeRegistry,
        *,
        audit: AuditWriter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        backoff_base: float = 1.0,
    ) -> None:
        self._repo = repository
        self._definitions = definitions
        self._registry = registry
        self._audit = audit
        self._sleep = sleep
        self._backoff_base = backoff_base

    async def execute(
        self, run: ClaimedRun, worker: str, renew: Callable[[], Awaitable[bool]]
    ) -> Literal["complete", "partial", "failed"]:
        ctx = RunContext(run.id, run.case_id, run.owner_user_id, run.definition, run.definition_version)
        await self._audit_event(AuditAction.WORKFLOW_START, run, {"count": run.attempts})

        definition = self._definitions.get(run.definition, run.definition_version)
        if definition is None:
            return await self._fail(run, worker, "definition_unavailable", None)
        missing = [n.type for n in definition.nodes if self._registry.get(n.type) is None]
        if missing:
            # All or nothing: never start a run that cannot finish.
            logger.warning("run %s needs unregistered node types: %s", run.id, sorted(set(missing)))
            return await self._fail(run, worker, "node_type_unavailable", None)

        steps = {s.node: s for s in await self._repo.load_steps(run.id)}
        if set(steps) != {n.id for n in definition.nodes}:
            return await self._fail(run, worker, "definition_mismatch", None)

        total = len(definition.nodes)
        try:
            for layer in definition.layers():
                if not await renew():
                    raise LeaseLostError
                todo = [n for n in layer if steps[n.id].status not in _FINISHED]
                outcomes = await asyncio.gather(*[self._run_node(ctx, n, steps[n.id]) for n in todo])
                failed = next((o for o in outcomes if o is not None), None)
                if failed is not None:
                    return await self._fail(run, worker, failed.code, failed)
                done = sum(1 for s in await self._repo.load_steps(run.id) if s.status in _FINISHED)
                await self._repo.set_progress(run.id, worker, done / total)
        except LeaseLostError:
            logger.warning("run %s: lease lost; stopping without writing a result", run.id)
            raise

        return await self._finish(run, worker)

    # ── one node: reuse, attempts, retry, timeout ──────────────────────────────────────────────
    async def _run_node(self, ctx: RunContext, spec: NodeSpec, step: StepRow) -> NodeError | None:
        """None on success; the `NodeError` when a CRITICAL node failed (a non-critical one is recorded
        as a failed step and makes the run partial)."""
        node = self._registry.get(spec.type)
        assert node is not None  # checked for every node before the run started
        ctx = dataclasses.replace(ctx, node_id=spec.id)
        fingerprint = getattr(node, "input_fingerprint", lambda _ctx: "")(ctx)
        digest = input_hash(ctx, spec, fingerprint)

        if await self._repo.has_reusable_result(ctx.case_id, spec.id, digest):
            await self._repo.start_step(step.id, digest)
            await self._repo.finish_step(step.id, "done")
            return None

        error: NodeError | None = None
        for attempt in range(spec.retries + 1):
            await self._repo.start_step(step.id, digest)
            try:
                async with asyncio.timeout(spec.timeout_s):
                    result = await node.run(ctx)
            except TimeoutError:
                error = RetryableError("timeout")
            except RetryableError as exc:
                error = exc
            except NodeError as exc:
                error = exc
                break  # a deliberate, non-retryable failure
            except Exception as exc:
                # Type only: the message could contain document content.
                logger.error("node %s raised %s", spec.id, type(exc).__name__)
                error = NodeError("internal_error")
                break
            else:
                await self._repo.finish_step(step.id, result.status, note=result.note)
                return None
            if attempt < spec.retries:
                await self._sleep(min(self._backoff_base * 2**attempt, 30.0))

        assert error is not None
        await self._repo.finish_step(
            step.id, "failed", note=error.note or DEFAULT_STEP_NOTE, error_code=error.code
        )
        return error if spec.critical else None

    # ── run outcome ────────────────────────────────────────────────────────────────────────────
    async def _finish(self, run: ClaimedRun, worker: str) -> Literal["complete", "partial"]:
        steps = await self._repo.load_steps(run.id)
        notes = await self._warning_notes(run.id)
        partial = any(s.status in {"warning", "failed"} for s in steps)
        status: Literal["complete", "partial"] = "partial" if partial else "complete"
        warnings = notes or (
            ["Some steps could not be completed. The report says so wherever it matters."] if partial else []
        )
        if not await self._repo.finish_run(run.id, worker, status, warnings=warnings):
            raise LeaseLostError
        await self._audit_event(AuditAction.WORKFLOW_FINISH, run, {"status": status})
        return status

    async def _warning_notes(self, run_id: uuid.UUID) -> list[str]:
        # Notes of warning/failed steps are fixed, person-safe strings (see StepResult.note).
        return list(dict.fromkeys(await self._repo.warning_notes(run_id)))  # distinct, in step order

    async def _fail(
        self, run: ClaimedRun, worker: str, code: str, error: NodeError | None
    ) -> Literal["failed"]:
        failure = {
            "title": (error.title if error else None) or DEFAULT_FAILURE_TITLE,
            "body": (error.body if error else None) or DEFAULT_FAILURE_BODY,
            "code": code,
        }
        if not await self._repo.finish_run(run.id, worker, "failed", failure=failure):
            raise LeaseLostError
        await self._audit_event(AuditAction.WORKFLOW_FINISH, run, {"status": "failed"})
        return "failed"

    async def _audit_event(
        self, action: AuditAction, run: ClaimedRun, metadata: dict[str, str | int]
    ) -> None:
        if self._audit is None:
            return
        await self._audit.record_completed(
            action,
            actor=run.owner_user_id,
            target_type="workflow_run",
            target_id=str(run.id),
            metadata=metadata,
        )
