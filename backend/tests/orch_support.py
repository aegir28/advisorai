"""A complete offline orchestration rig: in-memory store, fake storage, scripted fake provider, real registry
config with every agent enabled. It is how the reference orchestrator (a Python stand-in for the n8n master
workflow) drives a run end to end in tests, including failures."""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agents.registry import SpecialtyRegistry
from app.ai.providers.fake import FakeProvider
from app.ai.types import ModelRequest
from app.orchestration.policy import OrchestrationPolicy
from app.orchestration.service import OrchestrationService
from app.orchestration.stages import STAGE_IDS
from app.orchestration.store import CaseInputs, DocInfo, InMemoryOrchestrationStore
from app.router.signals import SignalExtractor
from app.storage.gateway import ObjectNotFoundError, StoragePath
from tests.ai_support import make_gateway
from tests.docs_support import make_pdf

OWNER = uuid.UUID("11111111-1111-4111-8111-111111111111")
CASE = uuid.UUID("22222222-2222-4222-8222-222222222222")
DOC = uuid.UUID("33333333-3333-4333-8333-333333333333")
DOC8 = str(DOC)[:8]
PAGE = (
    "Metformin 500 mg twice daily for type 2 diabetes.\n"
    "HbA1c was 8.2 % on 12 March 2026.\n"
    "Increased thirst for three months."
)
SNIPPETS = ["Metformin 500 mg twice daily", "HbA1c was 8.2 %", "Increased thirst for three months"]
F_MED, F_LAB, F_SYM = (f"f_{DOC8}_{n}" for n in (1, 2, 3))


class FakeStorage:
    def __init__(self, objects: dict[uuid.UUID, bytes]) -> None:
        self.objects = objects

    async def read_object(self, path: StoragePath, *, max_bytes: int) -> bytes:
        try:
            return self.objects[path.document_id][:max_bytes]
        except KeyError:
            raise ObjectNotFoundError("missing") from None

    async def create_download_url(self, path: StoragePath) -> Any:
        raise NotImplementedError

    async def create_upload_url(self, path: StoragePath) -> Any:
        raise NotImplementedError

    async def delete_objects(self, paths: list[StoragePath]) -> None:
        raise NotImplementedError


def facts_json() -> str:
    def fact(category: str, text: str, snippet: str, **extra: Any) -> dict[str, Any]:
        return {
            "category": category,
            "text": text,
            "confidence": "high",
            "page": 1,
            "snippet": snippet,
            **extra,
        }

    return json.dumps(
        {
            "facts": [
                fact("medication", "Metformin", SNIPPETS[0], value="500", unit="mg"),
                fact("lab_result", "HbA1c", SNIPPETS[1], value="8.2", unit="%", date="12 March 2026"),
                fact("symptom", "Increased thirst", SNIPPETS[2]),
            ]
        }
    )


def specialist_json(medication: bool = False, statement: str | None = None) -> str:
    body: dict[str, Any] = {
        "status": "complete",
        "confidence": {"overall": "moderate", "reason": "Based on three documented items."},
        "findings": [
            {
                "id": "fd1",
                "statement": statement or "Metformin 500 mg twice daily is documented for type 2 diabetes.",
                "kind": "patient_fact",
                "importance": "high",
                "fact_refs": [F_MED],
            },
            {
                "id": "fd2",
                "statement": "HbA1c was 8.2 % on 12 March 2026.",
                "kind": "patient_fact",
                "importance": "medium",
                "fact_refs": [F_LAB],
            },
        ],
        "uncertainties": [
            {"id": "u1", "text": "It is not clear how long metformin was taken.", "impact": "medium"}
        ],
        "missing_info": [
            {"id": "m1", "item": "Kidney function results", "why_it_matters": "They help judge safety."}
        ],
        "contradictions": [],
        "considerations": [],
        "questions": [
            {"id": "q1", "text": "How long has this dose been used?", "priority": 2, "linked_to": ["u1"]}
        ],
        "evidence_refs": [],
        "limitations": ["Only the uploaded documents were reviewed."],
    }
    if medication:
        body["medication_review"] = {
            "schema_version": "medication_review.v1",
            "medicines": [
                {
                    "id": "med1",
                    "medication": "Metformin",
                    "fact_refs": [F_MED],
                    "purpose": {"status": "documented", "value": "type 2 diabetes"},
                    "dose": {"status": "documented", "value": "500 mg"},
                    "frequency": {"status": "documented", "value": "twice daily"},
                    "duration": {"status": "not_documented"},
                }
            ],
            "concerns": [
                {
                    "id": "mc1",
                    "kind": "duration_not_documented",
                    "statement": "How long Metformin has been taken is not written in the record.",
                    "basis": "patient_record",
                    "medication_ids": ["med1"],
                    "fact_refs": [F_MED],
                    "source_ids": [],
                }
            ],
            "discussion_points": [
                {"id": "dp1", "text": "Ask how long Metformin has been used.", "linked_to": ["mc1"]}
            ],
            "missing_information": ["Duration of treatment"],
            "limitations": ["Only documented medicines were reviewed."],
        }
    return json.dumps(body)


def review_json() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "text": "Your records show you take Metformin for type 2 diabetes.",
                    "kind": "patient_fact",
                    "group": "fact",
                    "confidence": "high",
                    "derived_from": ["cl_general_medicine_fd1"],
                },
                {
                    "text": "Your HbA1c on 12 March 2026 was 8.2 %.",
                    "kind": "patient_fact",
                    "group": "fact",
                    "confidence": "high",
                    "derived_from": ["cl_general_medicine_fd2"],
                },
            ]
        }
    )


def questions_json() -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "audience": "current_doctor",
                    "priority": 1,
                    "category": "treatment",
                    "text": "How long should this plan be followed before it is reviewed?",
                    "trigger_kind": "treatment",
                    "linked_item_ids": ["syn_1"],
                }
            ]
        }
    )


Responder = Callable[[ModelRequest], str]


def default_responder(overrides: dict[str, Responder] | None = None) -> Responder:
    overrides = overrides or {}

    def respond(request: ModelRequest) -> str:
        key = request.schema_name
        if key == "SpecialistModelOutput":
            medication = "medicine perspective" in request.messages[0].content
            key = "SpecialistModelOutput:medication" if medication else "SpecialistModelOutput:general"
        if key in overrides:
            return overrides[key](request)
        if request.schema_name == "FactsModelOutput":
            return facts_json()
        if key.startswith("SpecialistModelOutput"):
            return specialist_json(medication=key.endswith("medication"))
        if request.schema_name == "ReviewModelOutput":
            return review_json()
        if request.schema_name == "QuestionsModelOutput":
            return questions_json()
        return json.dumps({})

    return respond


@dataclass
class Rig:
    service: OrchestrationService
    store: InMemoryOrchestrationStore
    provider: FakeProvider
    run_id: uuid.UUID
    usage: Any


async def make_rig(
    *,
    responders: dict[str, Responder] | None = None,
    pdf: bytes | None = None,
    enabled: tuple[str, ...] = ("general_medicine", "medication_safety"),
) -> Rig:
    store = InMemoryOrchestrationStore()
    store.inputs[CASE] = CaseInputs(
        CASE,
        OWNER,
        "I want a second opinion on my diabetes treatment.",
        None,
        "second_opinion",
        52,
        "F",
        [DocInfo(str(DOC), "lab", "ready", f"{OWNER}/{CASE}/{DOC}", "application/pdf", 1000, 1)],
    )
    run_id, _ = await store.create_run(OWNER, CASE, "test-key-0001", "case_analysis")
    provider = FakeProvider(responder=default_responder(responders))
    gateway, provider, sink, _ = make_gateway(provider)
    registry = SpecialtyRegistry.from_file()
    registry = SpecialtyRegistry(
        [s.model_copy(update={"enabled": s.id in enabled}) for s in registry.specs()]
    )
    service = OrchestrationService(
        store,
        gateway,
        registry,
        OrchestrationPolicy.from_file(),
        SignalExtractor.from_file(),
        storage=FakeStorage({DOC: pdf if pdf is not None else make_pdf([PAGE])}),
    )
    return Rig(service, store, provider, run_id, sink)


async def drive(rig: Rig) -> dict[str, str]:
    """The reference orchestrator: what the n8n master workflow does, in Python. Returns stage -> status."""
    svc, run_id = rig.service, rig.run_id
    await svc.begin(run_id)
    out: dict[str, str] = {}
    for stage_id in STAGE_IDS:
        result = await svc.run_stage(run_id, stage_id)
        out[stage_id] = result.status
        if result.status == "failed":
            break
        if stage_id == "specialist_fanout":
            plan = await svc.run_plan(run_id)
            for agent in plan.agents:  # n8n: SplitInBatches, max_parallel at a time
                await svc.run_agent(run_id, agent.id)
    out["finish"] = (await svc.finish(run_id)).status
    return out
