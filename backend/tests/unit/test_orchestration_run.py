"""A whole analysis run through the stage service with the fake provider: happy path, failures, retries, cost."""

import json
import uuid

import pytest

from app.ai.types import ProviderUnavailableError
from app.orchestration.contracts import CaseContext, SpecialistArtifact, SynthesisArtifact
from app.orchestration.stages import STAGE_IDS
from app.schemas.report import PatientReport
from tests.orch_support import DOC, F_MED, Rig, drive, make_rig, specialist_json

pytestmark = pytest.mark.anyio


async def report_of(rig: Rig) -> PatientReport:
    report = await rig.service.final_report(rig.run_id)
    assert report is not None
    return report


async def test_a_full_run_completes_and_produces_a_nineteen_section_report() -> None:
    rig = await make_rig()
    result = await drive(rig)
    assert result["finish"] in {"complete", "partial"}
    assert [result[s] for s in ("document_text", "fact_extraction", "routing", "specialist_collect")] == [
        "ok"
    ] * 4
    report = await report_of(rig)
    assert [s.number for s in report.sections] == list(range(1, 20))
    assert "not a diagnosis" in report.sections[18].items[0].text
    run = await rig.store.get_run(rig.run_id)
    assert run is not None and run.status in {"complete", "partial"}


async def test_every_stage_has_a_step_status_and_the_run_has_exactly_the_fourteen_stages() -> None:
    rig = await make_rig()
    await drive(rig)
    steps = await rig.store.step_statuses(rig.run_id)
    assert list(STAGE_IDS) == [s for s in STAGE_IDS if s in steps] and len(STAGE_IDS) == 14
    assert all(status != "running" for status, _, _ in steps.values())


async def test_the_case_context_is_deidentified_structured_and_indexes_the_evidence() -> None:
    rig = await make_rig()
    await drive(rig)
    art = await rig.store.get_artifact(rig.run_id, "case_context")
    assert art is not None
    ctx = CaseContext.model_validate(art.payload)
    assert [m.name for m in ctx.case.medications] == ["Metformin"]
    assert {e.id for e in ctx.evidence_index} == {
        f"ev_{f}" for f in (F_MED, F_MED[:-1] + "2", F_MED[:-1] + "3")
    }
    dumped = json.dumps(art.payload)
    assert "asha" not in dumped.lower() and "@" not in dumped


async def test_a_stage_retried_returns_the_stored_result_and_is_not_billed_again() -> None:
    rig = await make_rig()
    await drive(rig)
    calls = len(rig.provider.requests)
    again = await rig.service.run_stage(rig.run_id, "fact_extraction")
    # Not cached for a finished run? Stage artifacts are read-only after finish; a re-run must not call a model.
    assert again.cached is True and len(rig.provider.requests) == calls


async def test_an_agent_rerun_is_idempotent() -> None:
    rig = await make_rig()
    await rig.service.begin(rig.run_id)
    for stage_id in STAGE_IDS[:7]:
        await rig.service.run_stage(rig.run_id, stage_id)
    first = await rig.service.run_agent(rig.run_id, "general_medicine")
    calls = len(rig.provider.requests)
    second = await rig.service.run_agent(rig.run_id, "general_medicine")
    assert (first.cached, second.cached) == (False, True) and len(rig.provider.requests) == calls


async def test_a_failing_specialist_becomes_an_unavailable_state_and_the_run_continues_partial() -> None:
    def down(_: object) -> str:
        raise ProviderUnavailableError()

    rig = await make_rig(responders={"SpecialistModelOutput:medication": down})
    result = await drive(rig)
    assert result["finish"] == "partial" and result["specialist_collect"] == "unavailable"
    art = await rig.store.get_artifact(rig.run_id, "specialist", "medication_safety")
    assert art is not None
    parsed = SpecialistArtifact.model_validate(art.payload)
    assert parsed.status == "unavailable" and parsed.report is None and parsed.reason_code
    report = await report_of(rig)
    texts = " ".join(i.text for s in report.sections for i in s.items)
    assert "could not be completed" in texts  # said honestly in the report, never invented


async def test_when_every_specialist_fails_the_run_fails_without_a_fabricated_report() -> None:
    def down(_: object) -> str:
        raise ProviderUnavailableError()

    rig = await make_rig(
        responders={"SpecialistModelOutput:medication": down, "SpecialistModelOutput:general": down}
    )
    result = await drive(rig)
    assert result["specialist_collect"] == "failed" and result["finish"] == "failed"
    assert await rig.service.final_report(rig.run_id) is None


async def test_a_specialist_that_invents_an_evidence_id_is_rejected_not_repaired() -> None:
    bad = json.loads(specialist_json())
    bad["findings"][0]["fact_refs"] = ["f_nonexistent_9"]
    rig = await make_rig(responders={"SpecialistModelOutput:general": lambda _: json.dumps(bad)})
    await drive(rig)
    art = await rig.store.get_artifact(rig.run_id, "specialist", "general_medicine")
    assert (
        art is not None
        and art.payload["status"] == "unavailable"
        and art.payload["reason_code"] == "invalid_output"
    )


@pytest.mark.parametrize(
    "unsafe",
    [
        "You should stop taking Metformin.",
        "Start taking aspirin every day.",
        "Increase your dose of Metformin.",
        "Your doctor is wrong about this treatment.",
    ],
)
async def test_unsafe_specialist_output_is_blocked_before_it_is_stored(unsafe: str) -> None:
    rig = await make_rig(
        responders={"SpecialistModelOutput:general": lambda _: specialist_json(statement=unsafe)}
    )
    await drive(rig)
    art = await rig.store.get_artifact(rig.run_id, "specialist", "general_medicine")
    assert art is not None and art.payload["status"] == "unavailable"
    assert unsafe not in json.dumps((await rig.store.get_artifact(rig.run_id, "report")).payload)  # type: ignore[union-attr]


async def test_an_unsupported_claim_never_reaches_the_report() -> None:
    wrong = json.loads(specialist_json())
    wrong["findings"][1]["statement"] = (
        "HbA1c was 11.9 % on 12 March 2026."  # a number the record does not contain
    )
    rig = await make_rig(responders={"SpecialistModelOutput:general": lambda _: json.dumps(wrong)})
    await drive(rig)
    ver = await rig.store.get_artifact(rig.run_id, "verification")
    assert ver is not None
    removed = [c for c in ver.payload["claims"] if c.get("removed")]
    assert removed and "11.9" in removed[0]["text"]
    report_text = json.dumps((await rig.store.get_artifact(rig.run_id, "report")).payload)  # type: ignore[union-attr]
    assert "11.9" not in report_text


async def test_a_reviewer_that_cites_a_removed_claim_is_dropped_and_the_fallback_keeps_the_pipeline_going() -> (
    None
):
    def bad_review(_: object) -> str:
        return json.dumps(
            {
                "items": [
                    {
                        "text": "Everything is fine.",
                        "kind": "interpretation",
                        "group": "interpretation",
                        "confidence": "high",
                        "derived_from": ["cl_made_up_1"],
                    }
                ]
            }
        )

    rig = await make_rig(responders={"ReviewModelOutput": bad_review})
    result = await drive(rig)
    syn = SynthesisArtifact.model_validate((await rig.store.get_artifact(rig.run_id, "synthesis")).payload)  # type: ignore[union-attr]
    assert syn.produced_by == "fallback" and result["interim_review"] == "unavailable"
    assert all("Everything is fine" not in i.text for i in syn.synthesis.items)
    assert result["finish"] == "partial" and result["final_report"] == "ok"


async def test_unreadable_documents_are_disclosed_and_do_not_invent_content() -> None:
    from tests.docs_support import make_pdf

    rig = await make_rig(pdf=make_pdf([""]))  # a scan: no text layer, OCR is not available
    result = await drive(rig)
    assert result["document_text"] == "failed" and result["finish"] == "failed"
    assert await rig.service.final_report(rig.run_id) is None


async def test_cancellation_stops_the_run_and_nothing_further_is_processed() -> None:
    rig = await make_rig()
    await rig.service.begin(rig.run_id)
    await rig.service.run_stage(rig.run_id, "intake_safety")
    await rig.service.cancel(rig.run_id)
    after = await rig.service.run_stage(rig.run_id, "document_text")
    assert after.status == "cancelled" and rig.provider.requests == []
    assert (await rig.service.finish(rig.run_id)).status == "failed"


async def test_usage_is_recorded_per_call_with_run_case_agent_and_cost() -> None:
    rig = await make_rig()
    await drive(rig)
    records = rig.usage.records
    assert records and all(r.run_id == str(rig.run_id) and r.case_id for r in records)
    nodes = {r.node_id for r in records}
    assert {"agent:general_medicine", "agent:medication_safety", "fact_extraction", "interim_review"} <= nodes
    assert all(r.cost_micro_usd is not None for r in records)
    # identity never reached the provider
    assert all("@" not in m.content for req in rig.provider.requests for m in req.messages)


async def test_a_new_specialist_is_a_registry_entry_not_a_code_change() -> None:
    from app.agents.contracts import AgentSpec, Trigger
    from app.agents.registry import SpecialtyRegistry
    from app.orchestration.service import OrchestrationService

    rig = await make_rig()
    base = rig.service._reg.specs()
    new = AgentSpec(
        id="endocrinology",
        name="Endocrinology",
        version="0.1.0",
        tier=2,
        prompt_version=1,
        timeout_s=60,
        enabled=True,
        kind="specialty",
        focus="Looks at hormone and blood-sugar related findings.",
        prompt_mode="shared",
        triggers=[Trigger(signal="always", priority="optional", reason="Added from the registry.")],
    )
    svc = OrchestrationService(
        rig.service._store,
        rig.service._gw,
        SpecialtyRegistry([*base, new]),
        rig.service._policy,
        rig.service._extractor,
        storage=rig.service._storage,
    )
    rig2 = Rig(svc, rig.store, rig.provider, rig.run_id, rig.usage)
    await drive(rig2)
    art = await rig.store.get_artifact(rig.run_id, "specialist", "endocrinology")
    assert art is not None  # planned, run and stored through the same generic path
    assert isinstance(DOC, uuid.UUID)
