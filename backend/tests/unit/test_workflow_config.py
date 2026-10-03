"""The stage graph is configuration: loading, validation, and what changing it does to a real run.

Every test that says "config only" builds a workflow definition from the committed `registry/workflows.yaml`,
edits the DATA, and runs it through the same service and the same reference orchestrator. Nothing in the engine,
the handlers or the n8n workflows is touched.
"""

import copy
from typing import Any

import pytest
import yaml

from app.orchestration.contracts import SpecialistArtifact
from app.orchestration.workflows import (
    DEFAULT_FILE,
    MAX_STAGES,
    WorkflowConfigError,
    WorkflowRegistry,
)
from tests.docs_support import make_pdf
from tests.orch_support import CASE, DOC, PAGE, drive, make_rig

pytestmark = pytest.mark.anyio


def raw() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(DEFAULT_FILE.read_text(encoding="utf-8"))
    return copy.deepcopy(data["workflows"])


def registry(workflows: dict[str, Any]) -> WorkflowRegistry:
    return WorkflowRegistry.from_dict(workflows)


def stage(sid: str, handler: str = "checkpoint", **kw: Any) -> dict[str, Any]:
    return {"id": sid, "kind": "single", "handler": handler, "critical": False, **kw}


def index(stages: list[dict[str, Any]], sid: str) -> int:
    return next(i for i, s in enumerate(stages) if s["id"] == sid)


# ── loading and validation ───────────────────────────────────────────────────────────────────────
def test_the_committed_definitions_load_and_every_handler_exists_at_service_start() -> None:
    reg = WorkflowRegistry.from_file()
    assert set(reg.ids()) == {"case_analysis", "second_opinion"}
    assert len(reg.get("case_analysis").stages) == 14  # a property of THIS config, not of the engine


def test_the_stage_limit_matches_the_database_and_the_wire_contract() -> None:
    from tests.unit.test_db_contract_parity import MIGRATIONS, SCHEMAS_TS

    assert f"check (n between 1 and {MAX_STAGES})" in MIGRATIONS
    assert f"max({MAX_STAGES})" in SCHEMAS_TS


@pytest.mark.parametrize(
    ("edit", "code"),
    [
        (lambda s: s.append(stage("intake_safety")), "duplicate_stage"),
        (lambda s: s.insert(0, stage("early", depends_on=["intake_safety"])), "dependency_not_earlier"),
        (lambda s: s.insert(1, stage("gated", when="never_declared")), "when_flag_not_declared_earlier"),
        (lambda s: s.insert(0, stage("Bad-Name")), "bad_stage_name"),
        (lambda s: s.insert(0, stage("xx", flags=["Bad Flag"])), "bad_flag_name"),
        (lambda s: s.insert(1, stage("late_flag", when="needs_ocr")), "when_flag_not_declared_earlier"),
    ],
)
def test_a_malformed_graph_is_refused_with_a_fixed_code(edit: Any, code: str) -> None:
    wfs = raw()
    edit(wfs["case_analysis"]["stages"])
    with pytest.raises(WorkflowConfigError, match=code):
        registry(wfs)


def test_an_unknown_handler_or_a_kind_the_handler_cannot_do_is_refused_at_startup() -> None:
    reg = registry({"ww": {"version": 1, "stages": [stage("aa", handler="nope")]}})
    with pytest.raises(WorkflowConfigError, match="handler_unknown"):
        reg.check_handlers({"checkpoint": ["single"]})
    fan = registry({"ww": {"version": 1, "stages": [{**stage("aa"), "kind": "fanout"}]}})
    with pytest.raises(WorkflowConfigError, match="handler_kind_mismatch"):
        fan.check_handlers({"checkpoint": ["single"]})
    with pytest.raises(WorkflowConfigError):
        registry({"ww": {"version": 1, "stages": []}})
    with pytest.raises(WorkflowConfigError):
        registry({"ww": {"version": 1, "stages": [stage(f"s{i:02d}") for i in range(MAX_STAGES + 1)]}})


# ── config only: add / reorder / fan out / condition ─────────────────────────────────────────────
async def test_adding_a_stage_is_config_only() -> None:
    wfs = raw()
    stages = wfs["case_analysis"]["stages"]
    stages.insert(index(stages, "final_report"), stage("extra_checkpoint", depends_on=["interim_review"]))
    rig = await make_rig(workflows=registry(wfs))
    result = await drive(rig)
    assert result["extra_checkpoint"] == "ok" and result["finish"] in {"complete", "partial"}
    steps = await rig.store.step_statuses(rig.run_id)
    assert len(steps) == 15 and "extra_checkpoint" in steps  # no 14-stage assumption anywhere
    begin = await rig.service.begin(rig.run_id)
    assert [s.id for s in begin.stages].index("extra_checkpoint") == 13


async def test_adding_a_fanout_stage_is_config_only() -> None:
    wfs = raw()
    stages = wfs["case_analysis"]["stages"]
    at = index(stages, "specialist_fanout")
    # One fan-out becomes two, with the same handler and different params. No code, no n8n change.
    stages[at] = {**stages[at], "id": "specialists_mandatory", "params": {"priority": "mandatory"}}
    stages.insert(
        at + 1,
        {
            **stages[at],
            "id": "specialists_optional",
            "params": {"priority": "optional"},
            "depends_on": ["specialists_mandatory"],
        },
    )
    stages[index(stages, "specialist_collect")]["depends_on"] = ["specialists_optional"]
    rig = await make_rig(workflows=registry(wfs))
    result = await drive(rig)
    assert result["specialists_mandatory"] == "ok" and result["specialists_optional"] == "ok"
    mandatory = await rig.service.fanout_plan(rig.run_id, "specialists_mandatory")
    optional = await rig.service.fanout_plan(rig.run_id, "specialists_optional")
    assert {i.id for i in mandatory.items}.isdisjoint({i.id for i in optional.items})
    assert {i.id for i in mandatory.items} | {i.id for i in optional.items} == {
        "general_medicine",
        "medication_safety",
    }
    for agent in ("general_medicine", "medication_safety"):
        art = await rig.store.get_artifact(rig.run_id, "specialist", agent)
        assert art is not None and SpecialistArtifact.model_validate(art.payload).status == "ok"
    assert result["finish"] in {"complete", "partial"}


async def test_an_item_outside_a_fanout_stages_plan_is_refused() -> None:
    from app.orchestration.service import StageError

    wfs = raw()
    stages = wfs["case_analysis"]["stages"]
    stages[index(stages, "specialist_fanout")]["params"] = {"priority": "optional"}
    rig = await make_rig(workflows=registry(wfs))
    await rig.service.begin(rig.run_id)
    for sid in (
        "intake_safety",
        "document_text",
        "fact_extraction",
        "case_structuring",
        "routing",
        "specialist_fanout",
    ):
        await rig.service.run_stage(rig.run_id, sid)
    with pytest.raises(StageError, match="item_not_planned"):
        await rig.service.run_item(
            rig.run_id, "specialist_fanout", "general_medicine"
        )  # mandatory: not in this plan


async def test_changing_the_order_of_independent_stages_is_config_only() -> None:
    wfs = raw()
    stages = wfs["case_analysis"]["stages"]
    moved = stages.pop(index(stages, "evidence_retrieval"))
    stages.insert(0, moved)
    rig = await make_rig(workflows=registry(wfs))
    result = await drive(rig)
    assert next(iter(result)) == "evidence_retrieval" and result["finish"] in {"complete", "partial"}
    steps = await rig.store.step_statuses(rig.run_id)
    assert next(iter(steps)) == "evidence_retrieval"


async def test_an_order_that_breaks_a_dependency_is_not_loadable() -> None:
    wfs = raw()
    stages = wfs["case_analysis"]["stages"]
    stages.insert(0, stages.pop(index(stages, "final_report")))  # final_report depends on stages after it
    with pytest.raises(WorkflowConfigError, match="dependency_not_earlier"):
        registry(wfs)


async def test_a_stage_runs_only_after_its_dependencies_finished() -> None:
    rig = await make_rig()
    await rig.service.begin(rig.run_id)
    blocked = await rig.service.run_stage(rig.run_id, "routing")  # case_structuring has not run
    assert blocked.status == "failed" and blocked.code == "dependency_not_met"


async def test_a_conditional_stage_is_skipped_with_its_reason_and_the_run_still_completes() -> None:
    rig = await make_rig()
    result = await drive(rig)
    assert result["vision_ocr"] == "skipped"  # needs_ocr is false: every document had a text layer
    steps = await rig.store.step_statuses(rig.run_id)
    assert steps["vision_ocr"][0] == "skipped" and steps["vision_ocr"][1] == "condition_not_met:needs_ocr"
    art = await rig.store.get_artifact(rig.run_id, "stage", "vision_ocr")
    assert (
        art is not None
        and art.payload["condition"] == "needs_ocr"
        and art.payload["code"] == "condition_not_met"
    )
    assert result["finish"] in {"complete", "partial"}


async def test_the_condition_is_met_when_the_flag_is_true_and_the_stage_then_runs() -> None:
    rig = await make_rig()
    scan = make_pdf([""])  # a second document with no text layer
    second = DOC.__class__("44444444-4444-4444-8444-444444444444")
    rig.service._storage.objects[second] = scan  # type: ignore[union-attr]
    inputs = rig.store.inputs[CASE]
    from dataclasses import replace

    from app.orchestration.store import DocInfo

    rig.store.inputs[CASE] = replace(
        inputs,
        documents=[*inputs.documents, DocInfo(str(second), "lab", "ready", "p", "application/pdf", 1, 1)],
    )
    result = await drive(rig)
    assert result["document_text"] == "unavailable" and result["vision_ocr"] == "unavailable"
    steps = await rig.store.step_statuses(rig.run_id)
    assert steps["vision_ocr"][1] == "ocr_not_available"  # honest: OCR does not exist yet
    assert result["finish"] == "partial"


async def test_cross_review_is_skipped_by_config_when_too_few_specialists_and_runs_when_enough() -> None:
    one = await make_rig(enabled=("general_medicine",))
    result = await drive(one)
    assert result["cross_review"] == "skipped" and result["finish"] in {"complete", "partial"}
    two = await make_rig()
    assert (await drive(two))["cross_review"] == "ok"


async def test_a_condition_on_a_flag_that_is_never_set_is_false() -> None:
    wfs = raw()
    stages = wfs["case_analysis"]["stages"]
    stages.insert(1, stage("declares", flags=["maybe"]))
    stages.insert(2, stage("gated", when="maybe"))
    rig = await make_rig(workflows=registry(wfs))
    result = await drive(rig)
    assert result["gated"] == "skipped"  # `declares` (a checkpoint) never sets the flag


async def test_a_stage_cannot_set_a_flag_it_did_not_declare() -> None:
    rig = await make_rig()
    await rig.service.begin(rig.run_id)
    result = await rig.service.run_stage(rig.run_id, "intake_safety")
    assert result.flags == {}  # intake declares none; undeclared flags are dropped, never smuggled to n8n


async def test_the_skip_endpoint_is_refused_when_the_backend_disagrees() -> None:
    from app.orchestration.service import StageError

    rig = await make_rig()
    await rig.service.begin(rig.run_id)
    with pytest.raises(StageError, match="skip_condition_mismatch"):
        await rig.service.skip_stage(rig.run_id, "intake_safety", "condition_not_met")  # has no condition
    with pytest.raises(StageError, match="skip_condition_mismatch"):
        await rig.service.skip_stage(rig.run_id, "vision_ocr", "because")  # wrong reason


async def test_per_stage_retry_and_timeout_overrides_reach_the_descriptors() -> None:
    wfs = raw()
    stages = wfs["case_analysis"]["stages"]
    stages[index(stages, "final_report")].update({"retries": 0, "backoff_seconds": 1, "timeout_seconds": 600})
    rig = await make_rig(workflows=registry(wfs))
    begin = await rig.service.begin(rig.run_id)
    by_id = {s.id: s for s in begin.stages}
    assert (
        by_id["final_report"].retries,
        by_id["final_report"].backoff_seconds,
        by_id["final_report"].timeout_seconds,
    ) == (0, 1, 600)
    policy = rig.service._policy
    assert (
        by_id["routing"].retries == policy.retry.stage_retries
        and by_id["routing"].timeout_seconds == policy.timeouts.stage_seconds
    )


async def test_a_resumed_run_starts_with_the_flags_and_finished_stages_it_already_has() -> None:
    rig = await make_rig()
    await rig.service.begin(rig.run_id)
    await rig.service.run_stage(rig.run_id, "intake_safety")
    await rig.service.run_stage(rig.run_id, "document_text")
    again = await rig.service.begin(rig.run_id)
    assert again.completed_stages == ["intake_safety", "document_text"] and again.flags == {
        "needs_ocr": False
    }


# ── a second workflow on the same machinery ──────────────────────────────────────────────────────
async def test_second_opinion_is_a_different_graph_on_the_same_engine_and_orchestrator() -> None:
    rig = await make_rig(workflow="second_opinion")
    begin = await rig.service.begin(rig.run_id)
    assert begin.workflow == "second_opinion" and [s.id for s in begin.stages][-1] == "comparison"
    assert len(begin.stages) == 6 and "specialist_fanout" not in {s.id for s in begin.stages}
    result = await drive(rig)  # the very same reference orchestrator as case_analysis
    assert result["case_structuring"] == "ok" and result["comparison"] == "unavailable"
    assert result["finish"] == "partial"  # honest: the comparison is not built
    steps = await rig.store.step_statuses(rig.run_id)
    assert len(steps) == 6
    assert {r.schema_name for r in rig.provider.requests} == {
        "FactsModelOutput"
    }  # no specialists, no reviewer
    assert await rig.service.final_report(rig.run_id) is None


async def test_a_run_of_one_workflow_cannot_run_another_workflows_stage() -> None:
    from app.orchestration.service import StageError

    rig = await make_rig(workflow="second_opinion")
    await rig.service.begin(rig.run_id)
    with pytest.raises(StageError, match="unknown_stage"):
        await rig.service.run_stage(rig.run_id, "final_report")


async def test_the_page_fixture_is_the_one_the_stages_read() -> None:
    assert "Metformin" in PAGE  # guards the shared fixture the tests above rely on
