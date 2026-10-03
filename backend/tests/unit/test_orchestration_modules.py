"""Unit tests for the pure orchestration modules: policy, stages, context, verification, cross-review, review,
questions, comparison, report, prompts, store idempotency. No provider, no database."""

import json
import uuid
from datetime import UTC, datetime

import pytest

from app.docintel.contracts import ExtractedFact
from app.orchestration import comparison, crossreview, questions, report, review, verification
from app.orchestration.context import build_case_context, record_text
from app.orchestration.contracts import (
    CaseContext,
    ComparisonModelOutput,
    DocumentBrief,
    ModelQuestion,
    QuestionsModelOutput,
    ReviewItem,
    RunSummary,
    SpecialistModelOutput,
)
from app.orchestration.policy import OrchestrationPolicy, PolicyError
from app.orchestration.promptstore import PromptError, load, specialist_prompt
from app.orchestration.store import CaseInputs, DocInfo, InMemoryOrchestrationStore
from app.orchestration.workflows import WorkflowRegistry
from app.schemas.evidence import Claim
from app.schemas.specialist_report import SpecialistReport
from app.schemas.synthesis import SynthesisReviewer
from tests.orch_support import CASE, DOC8, F_LAB, F_MED, OWNER, specialist_json

pytestmark = pytest.mark.anyio
DOC = str(uuid.uuid4())


def fact(n: int, category: str, text: str, snippet: str, **kw: object) -> ExtractedFact:
    return ExtractedFact.model_validate(
        {
            "id": f"f_{DOC8}_{n}",
            "doc_id": DOC,
            "category": category,
            "text": text,
            "entities": [],
            "confidence": "high",
            "source": {"doc_id": DOC, "page": 1, "snippet": snippet},
            **kw,
        }
    )


FACTS = [
    fact(1, "medication", "Metformin", "Metformin 500 mg twice daily", value="500", unit="mg"),
    fact(2, "lab_result", "HbA1c", "HbA1c was 8.2 %", value="8.2", unit="%", date="12 March 2026"),
    fact(3, "symptom", "Increased thirst", "Increased thirst for three months"),
]
INPUTS = CaseInputs(
    CASE, OWNER, "Second opinion on diabetes care.", "A new tablet", "second_opinion", 52, "F", []
)


def context() -> CaseContext:
    return build_case_context(
        INPUTS, FACTS, [DocumentBrief(doc_id=DOC, type="lab", pages=1, text_layer="full")], 0
    )


def make_report(agent: str = "general_medicine", **changes: object) -> SpecialistReport:
    out = SpecialistModelOutput.model_validate_json(specialist_json())
    data = {**out.model_dump(mode="json", exclude={"medication_review"}, exclude_none=True), **changes}
    return SpecialistReport.model_validate(
        {
            "schema_version": "specialist_report.v1",
            "id": f"sr_{agent}",
            "run_id": "r1",
            "case_id": str(CASE),
            "specialist": agent,
            "name": agent.replace("_", " ").title(),
            "version": "0.1.0",
            "tier": 2,
            "priority": "mandatory",
            "routing_reason": "test",
            **{k: v for k, v in data.items() if v is not None},
        }
    )


# ── policy / stages / prompts ────────────────────────────────────────────────────────────────────
def test_the_policy_file_loads_and_a_bad_policy_is_a_coded_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    policy = OrchestrationPolicy.from_file()
    assert policy.limits.max_parallel_agents <= policy.limits.max_active_agents
    bad = tmp_path / "p.yaml"
    bad.write_text("version: 1\nlimits: {}\n")
    with pytest.raises(PolicyError, match="orchestration_policy_invalid"):
        OrchestrationPolicy.from_file(bad)


def test_the_standard_workflow_is_loaded_from_config_with_questions_before_the_report() -> None:
    ids = WorkflowRegistry.from_file().get("case_analysis").stage_ids
    assert len(set(ids)) == len(ids)
    assert ids.index("personalized_questions") < ids.index("final_report")


def test_the_shared_specialist_prompt_takes_its_focus_from_the_registry_and_forbids_unsafe_advice() -> None:
    text = specialist_prompt("Looks at the heart.", medication=False).text
    assert "Looks at the heart." in text and "{{focus}}" not in text
    assert "Never tell the person to start, stop, change" in text and "Never say a doctor is wrong" in text
    assert "medicine perspective" in specialist_prompt("x", medication=True).text
    assert load("interim_review").id.startswith("interim_review_v1@")
    with pytest.raises(PromptError):
        load("does_not_exist")


# ── context ──────────────────────────────────────────────────────────────────────────────────────
def test_the_case_context_is_structured_indexed_and_traceable() -> None:
    ctx = context()
    assert [m.name for m in ctx.case.medications] == ["Metformin"] and ctx.case.demographics.age == 52
    assert {e.id for e in ctx.evidence_index} == {f"ev_{f.id}" for f in FACTS}
    assert ctx.case.investigations.labs[0].date == "2026-03-12"
    assert [t.fact_id for t in ctx.timeline] == [FACTS[1].id]
    assert record_text(ctx.case)[F_LAB].count("8.2") >= 1


# ── verification ─────────────────────────────────────────────────────────────────────────────────
def verify_text(text: str, refs: list[str], kind: str = "patient_fact"):  # type: ignore[no-untyped-def]
    ctx = context()
    by_fact = {e.id.removeprefix("ev_"): e for e in ctx.evidence_index}
    return verification.judge(text, kind, refs, [], by_fact, (), record_text(ctx.case))[0]  # type: ignore[arg-type]


def test_supported_partial_unclear_contradicted_and_insufficient_are_all_reachable() -> None:
    assert verify_text("Metformin 500 mg twice daily", [F_MED]).status == "supported"
    assert verify_text("The record mentions metformin use", [F_MED]).status in {
        "partially_supported",
        "supported",
    }
    assert verify_text("Completely unrelated sentence about weather", [F_MED]).status == "unclear"
    assert verify_text("HbA1c was 11.9 % on 12 March 2026", [F_LAB]).status == "contradicted"
    assert verify_text("Metformin is documented", []).status == "insufficient_evidence"
    assert verify_text("Metformin is documented", ["f_made_up"]).status == "insufficient_evidence"
    assert verify_text("A study shows benefit", [], "external_evidence").status == "insufficient_evidence"


def test_a_single_digit_label_is_not_treated_as_a_contradiction() -> None:
    assert verify_text("Metformin 500 mg is documented for type 2 diabetes", [F_MED]).status != "contradicted"


def test_removed_claims_stay_removed_whatever_a_verification_model_says() -> None:
    claims = verification.claims_from_reports([make_report()], context().evidence_index, ())
    bad = make_report(findings=[{**json.loads(specialist_json())["findings"][0], "fact_refs": ["f_made_up"]}])
    claims = verification.claims_from_reports([bad], context().evidence_index, ())
    assert claims[0].removed and claims[0].status == "insufficient_evidence"
    from app.orchestration.contracts import VerificationModelResult

    promoted = verification.apply_model_results(
        claims, [VerificationModelResult(claim_id=claims[0].id, status="supported", rationale="because")]
    )
    assert promoted[0].removed and promoted[0].status == "insufficient_evidence"


def test_a_model_may_move_an_unclear_claim_but_never_invent_an_unknown_claim_id() -> None:
    from app.orchestration.contracts import VerificationModelResult

    claims = verification.claims_from_reports(
        [
            make_report(
                findings=[{**json.loads(specialist_json())["findings"][0], "statement": "Something vague"}]
            )
        ],
        context().evidence_index,
        (),
    )
    out = verification.apply_model_results(
        claims,
        [
            VerificationModelResult(
                claim_id=claims[0].id, status="contradicted", rationale="not in the record"
            ),
            VerificationModelResult(claim_id="cl_unknown", status="supported", rationale="x"),
        ],
    )
    assert out[0].removed and len(out) == len(claims)


# ── cross-review & review: disagreement preserved, never voted ───────────────────────────────────
def two_views() -> tuple[list[SpecialistReport], list[Claim], CaseContext]:
    a = make_report("general_medicine")
    b = make_report(
        "cardiology",
        contradictions=[
            {"id": "c1", "description": "The record disagrees about the dose.", "between": [F_MED, F_LAB]}
        ],
    )
    ctx = context()
    claims = verification.claims_from_reports([a, b], ctx.evidence_index, ())
    return [a, b], claims, ctx


def test_cross_review_keeps_disagreement_and_missing_information_and_never_votes() -> None:
    reports, claims, ctx = two_views()
    data = crossreview.cross_review(reports, claims, ctx.evidence_index)
    rels = {r.relationship for r in data.rows}
    assert {"disagreement", "missing_info"} <= rels
    assert not any(w in json.dumps(data.model_dump()).lower() for w in ("majority", "winner", "correct view"))


def test_a_reviewer_that_smooths_a_disagreement_away_has_it_added_back() -> None:
    reports, claims, ctx = two_views()
    cross = crossreview.cross_review(reports, claims, ctx.evidence_index)
    ok, removed = review.known_ids(claims, cross, reports)
    kept, dropped = review.validate_items(
        [
            ReviewItem(
                text="All views agree.",
                kind="interpretation",
                group="agreement",
                confidence="high",
                derived_from=[cross.rows[0].id],
            )
        ],
        claims,
        ok,
        removed,
    )
    art = review.assemble(
        "r1",
        kept,
        cross,
        produced_by="model",
        reviewer=SynthesisReviewer(label="AI reviewer (not a doctor)", tier=2, escalated=False),
        dropped=dropped,
    )
    groups = {i.group for i in art.synthesis.items}
    assert "disagreement" in groups and "missing" in groups
    assert any(i.flag == "disagreement" for i in art.synthesis.items)


def test_reviewer_items_with_unknown_removed_or_unsafe_content_are_dropped() -> None:
    reports, claims, ctx = two_views()
    cross = crossreview.cross_review(reports, claims, ctx.evidence_index)
    ok, removed = review.known_ids(claims, cross, reports)
    good = claims[0].id
    items = [
        ReviewItem(
            text="Your record shows metformin.",
            kind="patient_fact",
            group="fact",
            confidence="high",
            derived_from=[good],
        ),
        ReviewItem(
            text="You should stop taking metformin.",
            kind="interpretation",
            group="medication",
            confidence="high",
            derived_from=[good],
        ),
        ReviewItem(
            text="Your doctor is wrong about this.",
            kind="interpretation",
            group="disagreement",
            confidence="high",
            derived_from=[good],
        ),
        ReviewItem(
            text="Invented support.",
            kind="interpretation",
            group="interpretation",
            confidence="high",
            derived_from=["cl_nope"],
        ),
    ]
    kept, dropped = review.validate_items(items, claims, ok, removed)
    assert [i.text for i in kept] == ["Your record shows metformin."]
    assert dropped == {"unsafe_text": 2, "unknown_source_id": 1}


def test_the_fallback_synthesis_uses_only_verified_claims() -> None:
    _, claims, _ = two_views()
    assert all(
        i.derived_from[0] in {c.id for c in claims if not c.removed} for i in review.fallback_items(claims)
    )
    assert review.fallback_items([c.model_copy(update={"removed": True}) for c in claims]) == []


# ── questions ────────────────────────────────────────────────────────────────────────────────────
def q(text: str, links: list[str], **kw: object) -> ModelQuestion:
    return ModelQuestion.model_validate(
        {
            "audience": "current_doctor",
            "priority": 1,
            "category": "c",
            "text": text,
            "trigger_kind": "treatment",
            "linked_item_ids": links,
            **kw,
        }
    )


def test_questions_must_be_real_questions_linked_to_real_items_and_safe() -> None:
    out = QuestionsModelOutput(
        questions=[
            q("How long should this plan run?", ["syn_1"]),
            q("How long should this plan run?", ["syn_1"]),
            q("Stop the tablet.", ["syn_1"]),
            q("Should I stop taking metformin today?", ["syn_9"]),
            q("Should you stop taking metformin now?", ["syn_1"]),
        ]
    )
    kept, dropped = questions.validate_questions(out, {"syn_1"})
    assert [k.text for k in kept][:1] == ["How long should this plan run?"]
    assert dropped["duplicate"] == 1 and dropped["not_a_question"] == 1 and dropped["unknown_link"] == 1


def test_the_floor_adds_questions_for_disagreement_missing_and_medicine_items() -> None:
    reports, claims, ctx = two_views()
    cross = crossreview.cross_review(reports, claims, ctx.evidence_index)
    art = review.assemble(
        "r1",
        review.fallback_items(claims),
        cross,
        produced_by="fallback",
        reviewer=SynthesisReviewer(label="AI reviewer (not a doctor)", tier=2, escalated=False),
        dropped={},
    )
    final = questions.to_questions(questions.with_floor([], art.synthesis), "run12345")
    kinds = {x.category for x in final}
    assert {"disagreement", "missing information"} <= kinds
    assert all(x.linked_item_ids and x.status == "not_asked" for x in final)
    assert [x.priority for x in final] == sorted(x.priority for x in final)


# ── comparison: never a winner ───────────────────────────────────────────────────────────────────
def test_a_comparison_never_looks_more_settled_than_its_evidence_and_has_no_verdict_field() -> None:
    from app.schemas.comparison import ComparisonRow

    assert not {"winner", "better", "score", "recommended"} & set(ComparisonRow.model_fields)
    out = ComparisonModelOutput.model_validate(
        {
            "rows": [
                {
                    "topic": "Dose",
                    "opinion_a": "Keep dose",
                    "opinion_b": "Keep dose",
                    "evidence_a": ["e1"],
                    "evidence_b": [],
                    "relationship": "agreement",
                    "item_ids": ["syn_1"],
                },
                {
                    "topic": "Plan",
                    "opinion_a": "Doctor A is better.",
                    "opinion_b": "Change",
                    "evidence_a": ["e1"],
                    "evidence_b": ["e1"],
                    "relationship": "differs",
                    "item_ids": ["syn_1"],
                },
                {
                    "topic": "Other",
                    "opinion_a": "x is clear",
                    "opinion_b": "y",
                    "evidence_a": ["zzz"],
                    "evidence_b": [],
                    "relationship": "differs",
                    "item_ids": ["syn_1"],
                },
            ],
            "next_questions": [
                {
                    "audience": "current_doctor",
                    "priority": 1,
                    "category": "c",
                    "text": "Why do the views differ?",
                    "trigger_kind": "disagreement",
                    "linked_item_ids": ["syn_1"],
                },
                {
                    "audience": "current_doctor",
                    "priority": 1,
                    "category": "c",
                    "text": "Switch to the second doctor.",
                    "trigger_kind": "disagreement",
                    "linked_item_ids": ["syn_1"],
                },
            ],
        }
    )
    result, dropped = comparison.build_comparison(
        out, {"e1", "syn_1"}, label_a="First opinion", label_b="Second opinion"
    )
    assert [r.relationship for r in result.rows] == [
        "unresolved"
    ]  # the ranking row and the unknown-id row are gone
    assert dropped == {"agreement_downgraded": 1, "unsafe_text": 1, "unknown_id": 1, "question_dropped": 1}
    assert [x.text for x in result.next_questions] == ["Why do the views differ?"]


# ── report ───────────────────────────────────────────────────────────────────────────────────────
def build_report(removed: frozenset[str] = frozenset(), unavailable: list[str] | None = None):  # type: ignore[no-untyped-def]
    reports, claims, ctx = two_views()
    cross = crossreview.cross_review(reports, claims, ctx.evidence_index)
    art = review.assemble(
        "r1",
        review.fallback_items(claims),
        cross,
        produced_by="fallback",
        reviewer=SynthesisReviewer(label="AI reviewer (not a doctor)", tier=2, escalated=False),
        dropped={},
    )
    qs = questions.to_questions(questions.with_floor([], art.synthesis), "run12345")
    summary = RunSummary(
        schema_version="run_summary.v1",
        agents_ok=["general_medicine"],
        agents_unavailable=unavailable or [],
        unreadable_documents=2,
        missing_info_branch=True,
        removed_claims=len(removed),
    )
    return report.assemble_report(
        report_id="rep_1",
        case_id=str(CASE),
        run_id="r1",
        context=ctx,
        synthesis=art,
        reports=reports,
        questions=qs,
        summary=summary,
        source_titles={},
        removed_claim_ids=removed,
        now=datetime(2026, 10, 3, tzinfo=UTC),
    )


def test_the_report_has_nineteen_sections_a_fixed_disclaimer_and_honest_notes() -> None:
    built = build_report(unavailable=["cardiology"])
    assert [s.number for s in built.sections] == list(range(1, 20))
    text = " ".join(i.text for s in built.sections for i in s.items)
    assert (
        "2 of your documents could not be read" in text
        and "cardiology perspective could not be completed" in text
    )
    assert "not a diagnosis" in built.sections[18].items[0].text
    assert report.report_safety(built) == []
    assert {s.question_audience for s in built.sections if s.number in (15, 16)} == {
        "current_doctor",
        "second_opinion_doctor",
    }


def test_every_non_template_report_item_is_traceable_and_removed_claims_are_absent() -> None:
    built = build_report(removed=frozenset({"cl_general_medicine_fd2", "cl_cardiology_fd2"}))
    items = [i for s in built.sections for i in s.items if i.kind != "template"]
    assert items and all(i.id and i.evidence_ids for i in items)
    persp = [i for i in built.sections[11].items]
    assert not any("HbA1c" in i.text for i in persp)


def test_report_safety_catches_unsafe_text_that_slipped_in_and_reading_grade_is_measured() -> None:
    built = build_report()
    section = built.sections[0].model_copy(
        update={
            "items": [
                built.sections[1]
                .items[0]
                .model_copy(update={"text": "You should stop taking metformin.", "kind": "interpretation"})
            ]
        }
    )
    bad = built.model_copy(update={"sections": [section, *built.sections[1:]]})
    assert "medication_directive" in report.report_safety(bad)
    assert 0 < report.report_grade(built) < 20


# ── store idempotency ────────────────────────────────────────────────────────────────────────────
async def test_the_store_is_idempotent_per_run_and_refuses_writes_after_the_run_ends() -> None:
    store = InMemoryOrchestrationStore()
    store.inputs[CASE] = CaseInputs(
        CASE, OWNER, "c", None, None, 40, "M", [DocInfo("d", "lab", "ready", "p", None, None, None)]
    )
    run, created = await store.create_run(OWNER, CASE, "key-000001", "case_analysis", ["a"])
    again, created2 = await store.create_run(OWNER, CASE, "key-000001", "case_analysis", ["a"])
    assert (created, created2, run == again) == (True, False, True)
    _, new = await store.put_artifact(run, "k", "-", "k.v1", "ok", {"n": 1})
    b, new2 = await store.put_artifact(run, "k", "-", "k.v1", "ok", {"n": 2})
    assert new and not new2 and b.payload == {"n": 1}
    assert await store.load_case_inputs(run) is not None
    await store.finish_run(run, "complete", None, [])
    assert await store.load_case_inputs(run) is None  # the system path loses read access when the run ends
    with pytest.raises(PermissionError):
        await store.put_artifact(run, "other", "-", "k.v1", "ok", {})
