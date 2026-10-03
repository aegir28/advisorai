"""The stage service: what n8n calls, one capability at a time.

n8n sequences; this does the work. Each method is idempotent per (run, stage) or (run, agent): the result is an
append-only artifact, so a retried or resumed stage returns the stored result with `cached=True` and never
recomputes or re-bills. Every model call goes through the AI gateway (never a provider), every output is
validated and linted before it is stored, and a failure becomes an honest `unavailable` state, never an
invented result. Content never leaves this layer: n8n gets ids, statuses and counts.
"""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.contracts import AgentSpec, SpecialtyInput
from app.agents.prompts import PromptNotWrittenError, PromptStore
from app.agents.registry import SpecialtyRegistry
from app.agents.validate import errors, validate_medication_review, validate_specialist_report
from app.ai.gateway import AIGateway, GatewayRequest, PromptSegment
from app.ai.types import CallContext, GatewayError
from app.docintel.contracts import (
    DocumentText,
    ExtractedFact,
    ExtractionBatch,
    drop_unverified,
    verify_provenance,
)
from app.docintel.extract import ExtractionError, PypdfTextExtractor
from app.orchestration import comparison, crossreview, questions, report, review, verification
from app.orchestration.context import build_case_context
from app.orchestration.contracts import (
    AgentResult,
    BeginResult,
    CaseContext,
    ComparisonModelOutput,
    DocumentBrief,
    FactsModelOutput,
    FinishResult,
    PlannedAgent,
    QuestionsModelOutput,
    ReviewModelOutput,
    RoutingArtifact,
    RunPlan,
    RunSummary,
    SimplifiedModelOutput,
    SpecialistArtifact,
    SpecialistModelOutput,
    StageResult,
    SynthesisArtifact,
    VerificationArtifact,
    VerificationModelOutput,
)
from app.orchestration.policy import OrchestrationPolicy
from app.orchestration.promptstore import PromptError, load, specialist_prompt
from app.orchestration.stages import STAGE_IDS, STAGES, stage
from app.orchestration.store import CaseInputs, OrchestrationStore, RunRecord
from app.router.contracts import RouterInput
from app.router.guardrails import RequireReasonGuardrail
from app.router.router import Router
from app.router.signals import SignalExtractor
from app.router.strategies import RegistryRuleStrategy
from app.safety.output_lint import lint_document
from app.safety.readability import MAX_GRADE
from app.schemas.cross_review import CrossReviewData
from app.schemas.evidence import Claim
from app.schemas.medication_review import MedicationReview
from app.schemas.questions import Question
from app.schemas.report import PatientReport
from app.schemas.specialist_report import SpecialistReport
from app.schemas.synthesis import SynthesisReviewer
from app.storage.gateway import ObjectNotFoundError, StorageError, StorageGateway, StoragePath

logger = logging.getLogger("advisorai.orchestration")

MAX_DOC_BYTES = 15 * 1024 * 1024
MAX_PAGE_CHARS = 6000
MAX_DOC_CHARS = 24000
TEXT_ARTIFACT, FACTS_ARTIFACT = "document_text", "facts"


class StageError(Exception):
    """A stage could not do its job. `code` is a fixed string; `retryable` says whether a retry can help."""

    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.code, self.retryable = code, retryable


_Handler = Callable[[RunRecord], Awaitable[tuple[str, str | None, dict[str, int], dict[str, bool]]]]


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


class OrchestrationService:
    def __init__(
        self,
        store: OrchestrationStore,
        gateway: AIGateway,
        registry: SpecialtyRegistry,
        policy: OrchestrationPolicy,
        extractor: SignalExtractor,
        *,
        storage: StorageGateway | None = None,
        prompts: PromptStore | None = None,
    ) -> None:
        self._store, self._gw, self._reg, self._policy = store, gateway, registry, policy
        self._extractor, self._storage, self._prompts = extractor, storage, prompts or PromptStore()
        self._handlers: dict[str, _Handler] = {
            "intake_safety": self._intake,
            "document_text": self._document_text,
            "vision_ocr": self._vision_ocr,
            "fact_extraction": self._fact_extraction,
            "case_structuring": self._case_structuring,
            "routing": self._routing,
            "specialist_fanout": self._fanout,
            "specialist_collect": self._collect,
            "evidence_retrieval": self._evidence_retrieval,
            "evidence_verification": self._verification,
            "cross_review": self._cross_review,
            "interim_review": self._interim_review,
            "personalized_questions": self._questions,
            "final_report": self._final_report,
        }

    # ═══ run lifecycle ═══════════════════════════════════════════════════════════════════════════════
    async def begin(self, run_id: uuid.UUID, execution_id: str | None = None) -> BeginResult:
        run = await self._run(run_id)
        await self._store.mark_running(run_id, execution_id)
        done = [
            s
            for s, (status, _, _) in (await self._store.step_statuses(run_id)).items()
            if status in {"done", "skipped", "warning"}
        ]
        p = self._policy
        return BeginResult(
            schema_version="begin_result.v1",
            run_id=str(run.id),
            workflow="case_analysis",
            stages=list(STAGE_IDS),
            completed_stages=[s for s in STAGE_IDS if s in done],
            stage_retries=p.retry.stage_retries,
            backoff_seconds=p.retry.backoff_seconds,
            stage_timeout_seconds=p.timeouts.stage_seconds,
            agent_timeout_seconds=p.timeouts.agent_seconds,
            max_parallel_agents=p.limits.max_parallel_agents,
        )

    async def run_stage(self, run_id: uuid.UUID, stage_id: str) -> StageResult:
        try:
            spec = stage(stage_id)
        except KeyError:
            raise StageError("unknown_stage") from None
        run = await self._run(run_id)
        cached = await self._store.get_artifact(run_id, "stage", stage_id)
        if cached is not None:
            return StageResult.model_validate({**cached.payload, "cached": True})
        if run.cancel_requested or run.status not in ("queued", "running"):
            await self._store.set_step(run_id, stage_id, "skipped", note="cancelled")
            return self._result(run_id, stage_id, "cancelled", "run_cancelled")
        await self._store.set_step(run_id, stage_id, "running")
        try:
            status, code, counts, flags = await self._handlers[stage_id](run)
        except StageError as exc:
            return await self._failed(run_id, stage_id, spec.critical, exc.code, exc.retryable)
        except GatewayError as exc:
            return await self._failed(run_id, stage_id, spec.critical, exc.args[0], exc.retryable)
        except (ValidationError, KeyError, ValueError):
            logger.exception("orchestration stage failed", extra={"stage": stage_id})
            return await self._failed(run_id, stage_id, spec.critical, "stage_internal_error", False)
        result = self._result(run_id, stage_id, status, code, counts=counts, flags=flags)
        await self._store.set_step(
            run_id,
            stage_id,
            {"ok": "done", "skipped": "skipped", "unavailable": "warning"}[status],
            note=code,
        )
        await self._store.put_artifact(
            run_id, "stage", stage_id, "stage_result.v1", "ok", _dump(result), reason_code=code
        )
        return result

    async def finish(self, run_id: uuid.UUID) -> FinishResult:
        run = await self._run(run_id)
        steps = await self._store.step_statuses(run_id)
        critical = {s.id for s in STAGES if s.critical}
        failed_critical = [s for s, (st, _, _) in steps.items() if st == "failed" and s in critical]
        warnings = [
            f"{s}: {code or note or 'incomplete'}"
            for s, (st, note, code) in steps.items()
            if st in {"warning", "failed"}
        ]
        if run.cancel_requested:
            status = "failed"
            failure = {
                "code": "run_cancelled",
                "title": "The analysis was stopped",
                "body": "You stopped this analysis. Nothing further was processed.",
            }
        elif failed_critical or not all(s in steps for s in critical):
            status, failure = (
                "failed",
                {
                    "code": failed_critical[0] if failed_critical else "run_incomplete",
                    "title": "We could not finish the analysis",
                    "body": "A required step could not be completed. You can try again.",
                },
            )
        else:
            status, failure = ("partial" if warnings else "complete"), None
        await self._store.finish_run(run_id, status, failure, warnings)
        return FinishResult(schema_version="finish_result.v1", run_id=str(run_id), status=status)  # type: ignore[arg-type]

    async def cancel(self, run_id: uuid.UUID) -> None:
        await self._run(run_id)
        await self._store.request_cancel(run_id)

    # ═══ helpers ═════════════════════════════════════════════════════════════════════════════════════
    async def _run(self, run_id: uuid.UUID) -> RunRecord:
        run = await self._store.get_run(run_id)
        if run is None:
            raise StageError("run_not_found")
        return run

    def _result(
        self,
        run_id: uuid.UUID,
        stage_id: str,
        status: str,
        code: str | None,
        *,
        counts: dict[str, int] | None = None,
        flags: dict[str, bool] | None = None,
        retryable: bool = False,
    ) -> StageResult:
        return StageResult(
            schema_version="stage_result.v1",
            run_id=str(run_id),
            stage=stage_id,
            status=status,  # type: ignore[arg-type]
            cached=False,
            code=code,
            retryable=retryable,
            counts=counts or {},
            flags=flags or {},
        )

    async def _failed(
        self, run_id: uuid.UUID, stage_id: str, critical: bool, code: str, retryable: bool
    ) -> StageResult:
        # Failures are not cached: n8n may retry, and a resume re-runs the stage.
        await self._store.set_step(
            run_id, stage_id, "failed" if critical else "warning", note=code, error_code=code
        )
        return self._result(
            run_id, stage_id, "failed" if critical else "unavailable", code, retryable=retryable
        )

    def _ctx(self, run: RunRecord, node: str, purpose: str) -> CallContext:
        return CallContext(
            run_id=str(run.id),
            case_id=str(run.case_id),
            owner_user_id=str(run.owner_user_id),
            node_id=node,
            purpose=purpose,
        )

    async def _load[T: BaseModel](self, run: RunRecord, kind: str, model: type[T], key: str = "-") -> T:
        art = await self._store.get_artifact(run.id, kind, key)
        if art is None:
            raise StageError(f"{kind}_missing")
        return model.model_validate(art.payload)

    async def _save(
        self, run: RunRecord, kind: str, model: BaseModel, version: str, *, key: str = "-", status: str = "ok"
    ) -> None:
        await self._store.put_artifact(run.id, kind, key, version, status, _dump(model))

    # ═══ stages 1-5: intake, documents, facts, case ══════════════════════════════════════════════════
    async def _intake(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        inputs = await self._store.load_case_inputs(run.id)
        if inputs is None:
            raise StageError("case_not_available")
        if not inputs.concern.strip():
            raise StageError("concern_missing")
        if len(inputs.documents) > self._policy.limits.max_documents:
            raise StageError("too_many_documents")
        ready = [d for d in inputs.documents if d.status in {"uploaded", "ready", "processed", "complete"}]
        return "ok", None, {"documents": len(inputs.documents), "ready": len(ready)}, {}

    async def _inputs(self, run: RunRecord) -> CaseInputs:
        inputs = await self._store.load_case_inputs(run.id)
        if inputs is None:
            raise StageError("case_not_available")
        return inputs

    async def _document_text(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        inputs = await self._inputs(run)
        if not inputs.documents:
            return "skipped", "no_documents", {"documents": 0}, {}
        if self._storage is None:
            raise StageError("storage_unavailable", retryable=True)
        extractor, readable, unreadable = PypdfTextExtractor(), 0, 0
        for doc in inputs.documents:
            if await self._store.get_artifact(run.id, TEXT_ARTIFACT, doc.id) is not None:
                readable += 1  # idempotent retry
                continue
            try:
                data = await self._storage.read_object(
                    StoragePath(inputs.owner_user_id, inputs.case_id, uuid.UUID(doc.id)),
                    max_bytes=MAX_DOC_BYTES,
                )
                text = await extractor.extract(data, doc.mime_type or "application/pdf", doc.id)
            except (ObjectNotFoundError, ExtractionError):
                unreadable += 1
                continue
            except StorageError:
                raise StageError("storage_unavailable", retryable=True) from None
            if text.text_layer == "none":
                unreadable += 1
                continue
            readable += 1
            await self._store.put_artifact(
                run.id, TEXT_ARTIFACT, doc.id, "document_text.v1", "ok", _dump(text)
            )
        if readable == 0:
            raise StageError("no_readable_documents")
        return (
            ("ok" if unreadable == 0 else "unavailable"),
            ("some_documents_unreadable" if unreadable else None),
            {"readable": readable, "unreadable": unreadable},
            {},
        )

    async def _vision_ocr(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        # OCR / vision extraction is not implemented: the stage says so instead of pretending.
        unreadable = await self._store.get_artifact(run.id, "stage", "document_text")
        n = unreadable.payload.get("counts", {}).get("unreadable", 0) if unreadable else 0
        if n:
            return "unavailable", "ocr_not_available", {"unreadable": n}, {}
        return "skipped", "ocr_not_needed", {}, {}

    async def _fact_extraction(
        self, run: RunRecord
    ) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        total, dropped = 0, 0
        prompt = load("fact_extraction")
        for art in await self._store.list_artifacts(run.id, TEXT_ARTIFACT):
            if await self._store.get_artifact(run.id, FACTS_ARTIFACT, art.key) is not None:
                continue
            text = DocumentText.model_validate(art.payload)
            body = "\n\n".join(
                f"[page {p.page}]\n{p.text[:MAX_PAGE_CHARS]}" for p in text.pages if p.has_text_layer
            )[:MAX_DOC_CHARS]
            result = await self._gw.invoke(
                GatewayRequest(
                    schema=FactsModelOutput,
                    system=prompt.text,
                    segments=[PromptSegment(body, "free_text")],
                    task="extraction",
                    max_output_tokens=3000,
                    context=self._ctx(run, "fact_extraction", "docintel.facts"),
                )
            )
            batch = ExtractionBatch(
                doc_id=art.key,
                facts=[
                    ExtractedFact.model_validate(
                        {
                            "id": f"f_{art.key[:8]}_{n}",
                            "doc_id": art.key,
                            "category": f.category,
                            "text": f.text,
                            "value": f.value,
                            "unit": f.unit,
                            "date": f.date,
                            "entities": [],
                            "confidence": f.confidence,
                            "source": {"doc_id": art.key, "page": f.page, "snippet": f.snippet},
                        }
                    )
                    for n, f in enumerate(result.output.facts, start=1)
                ],
            )
            kept = drop_unverified(batch, verify_provenance(batch, text))
            total += len(kept.facts)
            dropped += len(batch.facts) - len(kept.facts)
            await self._store.put_artifact(
                run.id, FACTS_ARTIFACT, art.key, "extraction_batch.v1", "ok", _dump(kept)
            )
        if total == 0 and not await self._store.list_artifacts(run.id, FACTS_ARTIFACT):
            raise StageError("no_facts_extracted")
        return "ok", None, {"facts": total, "dropped_unverified": dropped}, {}

    async def _facts(self, run: RunRecord) -> list[ExtractedFact]:
        out: list[ExtractedFact] = []
        for art in await self._store.list_artifacts(run.id, FACTS_ARTIFACT):
            out.extend(ExtractionBatch.model_validate(art.payload).facts)
        return out

    async def _case_structuring(
        self, run: RunRecord
    ) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        inputs = await self._inputs(run)
        facts = await self._facts(run)
        briefs: list[DocumentBrief] = []
        for art in await self._store.list_artifacts(run.id, TEXT_ARTIFACT):
            text = DocumentText.model_validate(art.payload)
            info = next((d for d in inputs.documents if d.id == art.key), None)
            briefs.append(
                DocumentBrief(
                    doc_id=art.key,
                    type=info.type if info else "other",
                    pages=len(text.pages),
                    text_layer=text.text_layer,
                )
            )
        unreadable = len(inputs.documents) - len(briefs)
        ctx = build_case_context(inputs, facts, briefs, max(unreadable, 0))
        await self._save(run, "case_context", ctx, "case_context.v1")
        return "ok", None, {"facts": len(facts), "evidence_items": len(ctx.evidence_index)}, {}

    # ═══ stage 6: routing ════════════════════════════════════════════════════════════════════════════
    async def _routing(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        ctx = await self._load(run, "case_context", CaseContext)
        router = Router(
            self._reg,
            [RegistryRuleStrategy(self._reg, self._extractor)],
            [RequireReasonGuardrail()],
            max_active_agents=self._policy.limits.max_active_agents,
        )
        decision = await router.route(RouterInput(case=ctx.case))
        if not decision.plan.selected:
            raise StageError("no_specialist_selected")
        tiers = {s.specialist: self._reg.spec(s.specialist).tier for s in decision.plan.selected}
        await self._save(
            run,
            "routing_plan",
            RoutingArtifact(
                schema_version="routing_plan.v1", plan=decision.plan, trace=decision.trace, agent_tiers=tiers
            ),
            "routing_plan.v1",
        )
        return "ok", None, {"selected": len(decision.plan.selected)}, self._flags(ctx)

    def _flags(self, ctx: CaseContext) -> dict[str, bool]:
        c = self._policy.conditions
        return {
            "missing_info_branch": len(ctx.evidence_index) < c.missing_info_branch_if_evidence_items_below,
        }

    async def run_plan(self, run_id: uuid.UUID) -> RunPlan:
        run = await self._run(run_id)
        routing = await self._load(run, "routing_plan", RoutingArtifact)
        ctx = await self._load(run, "case_context", CaseContext)
        agents = [
            PlannedAgent(
                id=s.specialist, priority=s.priority, timeout_s=self._reg.spec(s.specialist).timeout_s
            )
            for s in routing.plan.selected
        ]
        verification_done = await self._store.get_artifact(run_id, "verification")
        extra = False
        if verification_done is not None:
            extra = (
                VerificationArtifact.model_validate(verification_done.payload).counts.get("contradicted", 0)
                >= self._policy.conditions.extra_verification_if_contradicted_at_least
            )
        return RunPlan(
            schema_version="run_plan.v1",
            run_id=str(run_id),
            agents=agents,
            max_parallel=self._policy.limits.max_parallel_agents,
            extra_verification=extra,
            missing_info_branch=self._flags(ctx)["missing_info_branch"],
        )

    async def _fanout(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        plan = await self.run_plan(run.id)
        return "ok", None, {"agents": len(plan.agents)}, {"missing_info_branch": plan.missing_info_branch}

    # ═══ stages 7-8: specialists ═════════════════════════════════════════════════════════════════════
    async def run_agent(self, run_id: uuid.UUID, agent_id: str) -> AgentResult:
        run = await self._run(run_id)
        cached = await self._store.get_artifact(run_id, "specialist", agent_id)
        if cached is not None:
            art = SpecialistArtifact.model_validate(cached.payload)
            return self._agent_result(run_id, agent_id, art.status, art.reason_code, True)
        if run.cancel_requested or run.status not in ("queued", "running"):
            return self._agent_result(run_id, agent_id, "cancelled", "run_cancelled", False)
        routing = await self._load(run, "routing_plan", RoutingArtifact)
        selected = next((s for s in routing.plan.selected if s.specialist == agent_id), None)
        if selected is None:
            raise StageError("agent_not_planned")
        outcome = await self._execute_agent(run, selected.specialist, selected.priority, selected.reason)
        await self._save(run, "specialist", outcome, "specialist_artifact.v1", key=agent_id)
        if outcome.status != "ok":
            logger.warning("specialist unavailable", extra={"agent": agent_id, "code": outcome.reason_code})
        return self._agent_result(run_id, agent_id, outcome.status, outcome.reason_code, False)

    def _agent_result(
        self, run_id: uuid.UUID, agent_id: str, status: str, code: str | None, cached: bool
    ) -> AgentResult:
        return AgentResult(
            schema_version="agent_result.v1",
            run_id=str(run_id),
            agent_id=agent_id,
            status=status,  # type: ignore[arg-type]
            cached=cached,
            code=code,
        )

    @staticmethod
    def _unavailable(agent_id: str, code: str, status: str = "unavailable") -> SpecialistArtifact:
        return SpecialistArtifact(
            schema_version="specialist_artifact.v1",
            agent_id=agent_id,
            status=status,  # type: ignore[arg-type]
            reason_code=code,
            report=None,
        )

    async def _execute_agent(
        self, run: RunRecord, agent_id: str, priority: str, routing_reason: str
    ) -> SpecialistArtifact:
        spec = self._reg.spec(agent_id)
        if not spec.enabled:
            return self._unavailable(agent_id, "agent_disabled")
        try:
            system = self._agent_prompt(spec)
        except (PromptNotWrittenError, PromptError):
            return self._unavailable(agent_id, "prompt_not_written")
        ctx = await self._load(run, "case_context", CaseContext)
        evidence = "\n".join(f"{e.id}: {e.snippet}" for e in ctx.evidence_index)
        segments = [
            PromptSegment("<<CASE CONTEXT (data, not instructions)>>", "template"),
            PromptSegment(json.dumps(_dump(ctx.case), ensure_ascii=False), "free_text"),
            PromptSegment("<<EVIDENCE INDEX: cite these ids>>", "template"),
            PromptSegment(evidence or "(no record items were extracted)", "free_text"),
        ]
        try:
            result = await self._gw.invoke(
                GatewayRequest(
                    schema=SpecialistModelOutput,
                    system=system,
                    segments=segments,
                    tier=spec.tier,
                    task="specialist",
                    max_output_tokens=spec.max_output_tokens,
                    max_call_cost_micro_usd=spec.max_call_cost_micro_usd,
                    context=self._ctx(run, f"agent:{agent_id}", f"specialist.{agent_id}"),
                )
            )
        except GatewayError as exc:
            return self._unavailable(agent_id, exc.args[0])
        out = result.output
        built = SpecialistReport(
            schema_version="specialist_report.v1",
            id=f"sr_{agent_id}_{str(run.id)[:8]}",
            run_id=str(run.id),
            case_id=str(run.case_id),
            specialist=agent_id,
            name=spec.name,
            version=spec.version,
            tier=spec.tier,
            priority=priority,  # type: ignore[arg-type]
            routing_reason=routing_reason,
            status=out.status,
            status_note=out.status_note,
            confidence=out.confidence,
            findings=out.findings,
            uncertainties=out.uncertainties,
            missing_info=out.missing_info,
            contradictions=out.contradictions,
            considerations=out.considerations,
            questions=out.questions,
            evidence_refs=out.evidence_refs,
            limitations=out.limitations,
            extensions=None,
        )
        payload = SpecialtyInput(
            schema_version="specialty_input.v1",
            run_id=str(run.id),
            case=ctx.case,
            routing=_selection(agent_id, priority, routing_reason),
            sources=[],
        )
        if errors(validate_specialist_report(built, payload, spec)):
            return self._unavailable(agent_id, "invalid_output")
        if lint_document(_dump(built)):
            return self._unavailable(agent_id, "unsafe_output")
        if spec.extension == "medication_review":
            try:
                review_obj = MedicationReview.model_validate(out.medication_review or {})
            except ValidationError:
                return self._unavailable(agent_id, "invalid_medication_review")
            if errors(validate_medication_review(review_obj, ctx.case, set())):
                return self._unavailable(agent_id, "invalid_medication_review")
            built = built.model_copy(update={"extensions": {"medication_review": _dump(review_obj)}})
        return SpecialistArtifact(
            schema_version="specialist_artifact.v1", agent_id=agent_id, status="ok", report=built
        )

    def _agent_prompt(self, spec: AgentSpec) -> str:
        if spec.prompt_mode == "shared":
            return specialist_prompt(spec.focus, medication=spec.extension == "medication_review").text
        return self._prompts.get(spec.id, spec.prompt_version).text

    async def _collect(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        routing = await self._load(run, "routing_plan", RoutingArtifact)
        ok = unavailable = 0
        for sel in routing.plan.selected:
            art = await self._store.get_artifact(run.id, "specialist", sel.specialist)
            if art is None:  # never ran (cancelled, n8n lost it): recorded as unavailable, not invented
                await self._save(
                    run,
                    "specialist",
                    self._unavailable(sel.specialist, "not_run"),
                    "specialist_artifact.v1",
                    key=sel.specialist,
                )
                unavailable += 1
            elif art.status == "ok":
                ok += 1
            else:
                unavailable += 1
        if ok == 0:
            raise StageError("no_specialist_available")
        status = "ok" if unavailable == 0 else "unavailable"
        return (
            status,
            ("some_specialists_unavailable" if unavailable else None),
            {
                "ok": ok,
                "unavailable": unavailable,
            },
            {},
        )

    async def _reports(self, run: RunRecord) -> tuple[list[SpecialistReport], list[str]]:
        reports: list[SpecialistReport] = []
        down: list[str] = []
        for art in await self._store.list_artifacts(run.id, "specialist"):
            parsed = SpecialistArtifact.model_validate(art.payload)
            if parsed.status == "ok" and parsed.report is not None:
                reports.append(parsed.report)
            else:
                down.append(parsed.agent_id)
        return reports, down

    def _medication(self, reports: list[SpecialistReport]) -> dict[str, MedicationReview]:
        out: dict[str, MedicationReview] = {}
        for r in reports:
            raw = (r.extensions or {}).get("medication_review")
            if raw:
                out[r.specialist] = MedicationReview.model_validate(raw)
        return out

    # ═══ stages 9-11: evidence, verification, cross-review ═══════════════════════════════════════════
    async def _evidence_retrieval(
        self, run: RunRecord
    ) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        # No external evidence corpus or retriever is configured yet: say so rather than pretend.
        return "skipped", "no_external_corpus", {"external_sources": 0}, {}

    async def _verification(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        ctx = await self._load(run, "case_context", CaseContext)
        reports, _ = await self._reports(run)
        meds = self._medication(reports)
        concerns = {
            agent: [(c.id, c.statement, c.fact_refs, c.source_ids) for c in review_obj.concerns]
            for agent, review_obj in meds.items()
        }
        claims = verification.claims_from_reports(
            reports, ctx.evidence_index, (), medication_concerns=concerns
        )
        c = self._policy.conditions
        deep = False
        contradicted = sum(1 for x in claims if x.status == "contradicted")
        if c.verification_model_enabled and contradicted >= c.extra_verification_if_contradicted_at_least:
            deep = True
            claims = await self._model_verify(run, claims, ctx)
        art = VerificationArtifact(
            schema_version="verification.v1",
            claims=claims,
            counts=verification.counts(claims),
            mode="deep" if deep else "standard",
        )
        await self._save(run, "verification", art, "verification.v1")
        return "ok", None, art.counts, {"extra_verification": deep}

    async def _model_verify(self, run: RunRecord, claims: list[Claim], ctx: CaseContext) -> list[Claim]:
        pending = [x for x in claims if not x.removed and x.status in {"unclear", "partially_supported"}]
        if not pending:
            return claims
        by_fact = {e.id.removeprefix("ev_"): e.snippet for e in ctx.evidence_index}
        body = "\n".join(
            f"{x.id}: claim={x.text} | record={' '.join(by_fact.get(f, '') for f in x.patient_fact_ids)}"
            for x in pending
        )
        try:
            result = await self._gw.invoke(
                GatewayRequest(
                    schema=VerificationModelOutput,
                    system=load("claim_verification").text,
                    segments=[PromptSegment(body, "free_text")],
                    task="verification",
                    context=self._ctx(run, "evidence_verification", "verification.claims"),
                )
            )
        except GatewayError:
            return claims  # the deterministic floor stands
        return verification.apply_model_results(claims, result.output.results)

    async def _cross_review(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        ctx = await self._load(run, "case_context", CaseContext)
        reports, _ = await self._reports(run)
        ver = await self._load(run, "verification", VerificationArtifact)
        if len(reports) < self._policy.limits.min_specialists_for_cross_review:
            empty = CrossReviewData(specialists=[], rows=[])
            await self._save(run, "cross_review", empty, "cross_review.v1", status="skipped")
            return "skipped", "too_few_specialists", {"rows": 0}, {}
        data = crossreview.cross_review(reports, ver.claims, ctx.evidence_index, self._medication(reports))
        await self._save(run, "cross_review", data, "cross_review.v1")
        disagreements = sum(1 for r in data.rows if r.relationship in {"disagreement", "medication_conflict"})
        return "ok", None, {"rows": len(data.rows), "disagreements": disagreements}, {}

    # ═══ stage 12: interim clinical review ═══════════════════════════════════════════════════════════
    async def _interim_review(
        self, run: RunRecord
    ) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        reports, _ = await self._reports(run)
        ver = await self._load(run, "verification", VerificationArtifact)
        cross = await self._load(run, "cross_review", CrossReviewData)
        ok_ids, removed = review.known_ids(ver.claims, cross, reports)
        disagreements = sum(
            1 for r in cross.rows if r.relationship in {"disagreement", "medication_conflict"}
        )
        esc = self._policy.conditions.review_escalation
        escalated = disagreements >= esc.if_disagreements_at_least
        tier = esc.tier if escalated else 2
        reviewer = SynthesisReviewer(
            label="AI reviewer (not a doctor)",
            tier=tier,
            escalated=escalated,
            escalation_reason="Several perspectives disagree." if escalated else None,
        )
        body = json.dumps(
            {
                "claims": [
                    {"id": c.id, "text": c.text, "kind": c.kind, "status": c.status}
                    for c in review.usable(ver.claims)
                ],
                "cross_review": [
                    {"id": r.id, "topic": r.topic, "relationship": r.relationship, "summary": r.summary}
                    for r in cross.rows
                ],
            },
            ensure_ascii=False,
        )
        dropped: dict[str, int] = {}
        produced, items = "fallback", review.fallback_items(ver.claims)
        try:
            result = await self._gw.invoke(
                GatewayRequest(
                    schema=ReviewModelOutput,
                    system=load("interim_review").text,
                    segments=[PromptSegment(body, "free_text")],
                    tier=tier,
                    task="review",
                    max_output_tokens=3000,
                    context=self._ctx(run, "interim_review", "review.interim"),
                )
            )
            kept, dropped = review.validate_items(
                review.model_output_items(result.output), ver.claims, ok_ids, removed
            )
            if kept:
                produced, items = "model", kept
        except GatewayError as exc:
            dropped = {f"reviewer_{exc.args[0]}": 1}
        art = review.assemble(
            str(run.id), items, cross, produced_by=produced, reviewer=reviewer, dropped=dropped
        )
        await self._save(run, "synthesis", art, "synthesis_artifact.v1")
        status, code = ("ok", None) if produced == "model" else ("unavailable", "reviewer_fallback")
        return status, code, {"items": len(art.synthesis.items)}, {"escalated": escalated}

    # ═══ stage 13: questions ═════════════════════════════════════════════════════════════════════════
    async def _questions(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        syn = await self._load(run, "synthesis", SynthesisArtifact)
        known = {i.id for i in syn.synthesis.items}
        body = json.dumps(
            [{"id": i.id, "group": i.group, "text": i.text} for i in syn.synthesis.items], ensure_ascii=False
        )
        kept: list[Any] = []
        status, code = "ok", None
        try:
            result = await self._gw.invoke(
                GatewayRequest(
                    schema=QuestionsModelOutput,
                    system=load("questions").text,
                    segments=[PromptSegment(body, "free_text")],
                    task="questions",
                    context=self._ctx(run, "personalized_questions", "questions.personal"),
                )
            )
            kept, _ = questions.validate_questions(result.output, known)
        except GatewayError as exc:
            status, code = "unavailable", f"questions_{exc.args[0]}"
        final = questions.to_questions(questions.with_floor(kept, syn.synthesis), str(run.id))
        await self._store.put_artifact(
            run.id, "questions", "-", "questions.v1", "ok", {"questions": [_dump(q) for q in final]}
        )
        return status, code, {"questions": len(final)}, {}

    # ═══ stage 14: final report ══════════════════════════════════════════════════════════════════════
    async def _final_report(self, run: RunRecord) -> tuple[str, str | None, dict[str, int], dict[str, bool]]:
        ctx = await self._load(run, "case_context", CaseContext)
        syn = await self._load(run, "synthesis", SynthesisArtifact)
        ver = await self._load(run, "verification", VerificationArtifact)
        q_art = await self._store.get_artifact(run.id, "questions")
        qs = [Question.model_validate(q) for q in (q_art.payload["questions"] if q_art else [])]
        reports, down = await self._reports(run)
        summary = RunSummary(
            schema_version="run_summary.v1",
            agents_ok=[r.specialist for r in reports],
            agents_unavailable=down,
            unreadable_documents=ctx.unreadable_documents,
            missing_info_branch=self._flags(ctx)["missing_info_branch"],
            removed_claims=sum(1 for c in ver.claims if c.removed),
        )
        await self._save(run, "run_summary", summary, "run_summary.v1")
        built = report.assemble_report(
            report_id=f"rep_{run.id}",
            case_id=str(run.case_id),
            run_id=str(run.id),
            context=ctx,
            synthesis=syn,
            reports=reports,
            questions=qs,
            summary=summary,
            source_titles={},
        )
        built, simplified = await self._simplify_if_hard(run, built)
        violations = report.report_safety(built)
        if violations:
            # Unsafe text never ships: the offending items are removed and the removal is reported.
            built = _strip_unsafe(built)
            if report.report_safety(built):
                raise StageError("report_unsafe")
        grade = report.report_grade(built)
        await self._store.put_artifact(run.id, "report", "-", "report.v1", "ok", _dump(built))
        return (
            "ok",
            None,
            {
                "grade_x10": int(grade * 10),
                "removed_unsafe_items": len(violations),
                "simplified": int(simplified),
            },
            {"reading_level_ok": grade <= MAX_GRADE},
        )

    async def _simplify_if_hard(self, run: RunRecord, built: PatientReport) -> tuple[PatientReport, bool]:
        if report.report_grade(built) <= MAX_GRADE:
            return built, False
        items = {i.id: i.text for s in built.sections for i in s.items if i.id and i.kind != "template"}
        try:
            result = await self._gw.invoke(
                GatewayRequest(
                    schema=SimplifiedModelOutput,
                    system=load("report_simplify").text,
                    segments=[PromptSegment(json.dumps(items, ensure_ascii=False), "free_text")],
                    task="report",
                    max_output_tokens=4000,
                    context=self._ctx(run, "final_report", "report.simplify"),
                )
            )
        except GatewayError:
            return built, False
        new = {s.id: s.text for s in result.output.items if s.id in items}
        sections = [
            sec.model_copy(
                update={
                    "items": [
                        i.model_copy(update={"text": new[i.id]}) if i.id in new else i for i in sec.items
                    ]
                }
            )
            for sec in built.sections
        ]
        simplified = built.model_copy(update={"sections": sections})
        # Accept the rewrite only if it is easier AND still safe; otherwise keep the original.
        if report.report_grade(simplified) < report.report_grade(built) and not report.report_safety(
            simplified
        ):
            return simplified, True
        return built, False

    # ═══ read side (owner API) ═══════════════════════════════════════════════════════════════════════
    async def final_report(self, run_id: uuid.UUID) -> PatientReport | None:
        art = await self._store.get_artifact(run_id, "report")
        return PatientReport.model_validate(art.payload) if art else None

    async def comparison_for(
        self, run: RunRecord, a_label: str, b_label: str, output: ComparisonModelOutput
    ) -> tuple[Any, dict[str, int]]:
        syn = await self._load(run, "synthesis", SynthesisArtifact)
        known = {i.id for i in syn.synthesis.items}
        return comparison.build_comparison(output, known, label_a=a_label, label_b=b_label)


def _selection(agent_id: str, priority: str, reason: str) -> Any:
    from app.schemas.routing import RoutingSelection

    return RoutingSelection(specialist=agent_id, priority=priority, reason=reason)  # type: ignore[arg-type]


def _strip_unsafe(built: PatientReport) -> PatientReport:
    from app.safety.output_lint import lint_text

    sections = [
        sec.model_copy(
            update={"items": [i for i in sec.items if i.kind == "template" or not lint_text(i.text, i.kind)]}
        )
        for sec in built.sections
    ]
    return built.model_copy(update={"sections": sections})
