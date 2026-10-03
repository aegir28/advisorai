"""Router infrastructure: pipeline stages, caps, guardrails, strategy extension points. The rules used here are
arbitrary test rules (keyed on trivial case properties) and say nothing about real routing."""

import json
from pathlib import Path

import pytest

from app.agents.registry import SpecialtyRegistry
from app.ai.gateway import GatewayRequest, PromptSegment
from app.ai.providers.fake import FakeProvider, FakeStep
from app.router.contracts import Candidate, Proposal, RouterInput, RoutingError
from app.router.guardrails import AllowedSpecialtiesGuardrail, RequireReasonGuardrail
from app.router.router import Router
from app.router.strategies import LLMAssistedStrategy, RoutingProposal, Rule, RuleStrategy
from app.schemas import CaseV1
from tests.ai_support import make_gateway

pytestmark = pytest.mark.anyio

CASE = CaseV1.model_validate(
    json.loads(
        (
            Path(__file__).resolve().parents[1] / "fixtures" / "contracts" / "cardiology" / "case.v1.json"
        ).read_text()
    )
)
INPUT = RouterInput(case=CASE)


def enabled_registry(*ids: str) -> SpecialtyRegistry:
    base = SpecialtyRegistry.from_file()
    return SpecialtyRegistry([s.model_copy(update={"enabled": s.id in ids}) for s in base.specs()])


class Fixed:
    def __init__(self, name: str, *candidates: Candidate, missing: tuple[str, ...] = ()) -> None:
        self.name = name
        self._proposal = Proposal(candidates, missing)

    async def propose(self, routing_input: RouterInput) -> Proposal:
        return self._proposal


def cand(specialty: str, priority: str = "optional", reason: str = "because", by: str = "t") -> Candidate:
    return Candidate(specialty, priority, reason, by)  # type: ignore[arg-type]


async def test_with_no_strategy_the_router_selects_nobody_and_says_why() -> None:
    decision = await Router(enabled_registry("cardiology")).route(INPUT)
    assert decision.plan.selected == []
    assert decision.plan.missing_for_routing == ["No routing rules are configured yet."]
    assert "no routing strategy is configured" in decision.trace


async def test_selected_candidates_become_the_ui_routing_plan() -> None:
    router = Router(
        enabled_registry("cardiology", "general_medicine"),
        [Fixed("a", cand("general_medicine", "mandatory", "r1"), cand("cardiology", "optional", "r2"))],
    )
    plan = (await router.route(INPUT)).plan
    assert [(s.specialist, s.priority, s.reason) for s in plan.selected] == [
        ("general_medicine", "mandatory", "r1"),
        ("cardiology", "optional", "r2"),
    ]
    assert plan.not_selected == []


async def test_a_disabled_agent_is_never_selected_and_is_explained() -> None:
    router = Router(enabled_registry("cardiology"), [Fixed("a", cand("cardiology"), cand("neurology"))])
    decision = await router.route(INPUT)
    assert [s.specialist for s in decision.plan.selected] == ["cardiology"]
    assert [(n.name, n.why) for n in decision.plan.not_selected] == [("neurology", "agent is not enabled")]


async def test_strategies_are_merged_one_entry_per_specialty_mandatory_wins() -> None:
    router = Router(
        enabled_registry("cardiology"),
        [
            Fixed("a", cand("cardiology", "optional", "first")),
            Fixed("b", cand("cardiology", "mandatory", "second")),
        ],
    )
    (selected,) = (await router.route(INPUT)).plan.selected
    assert selected.priority == "mandatory" and selected.reason == "first; second"


async def test_the_active_agent_cap_drops_optional_candidates_last_first_and_says_so() -> None:
    ids = ("general_medicine", "cardiology", "neurology", "orthopedics")
    cands = [
        cand("general_medicine", "mandatory"),
        cand("cardiology"),
        cand("neurology"),
        cand("orthopedics"),
    ]
    decision = await Router(enabled_registry(*ids), [Fixed("a", *cands)], max_active_agents=2).route(INPUT)
    assert [s.specialist for s in decision.plan.selected] == ["general_medicine", "cardiology"]
    assert [(n.name, n.why) for n in decision.plan.not_selected] == [
        ("neurology", "active-agent limit reached"),
        ("orthopedics", "active-agent limit reached"),
    ]


async def test_more_mandatory_candidates_than_the_cap_fails_loudly_instead_of_dropping_one() -> None:
    router = Router(
        enabled_registry("cardiology", "neurology"),
        [Fixed("a", cand("cardiology", "mandatory"), cand("neurology", "mandatory"))],
        max_active_agents=1,
    )
    with pytest.raises(RoutingError) as exc:
        await router.route(INPUT)
    assert exc.value.code == "too_many_mandatory"


def test_a_cap_below_one_is_a_configuration_error() -> None:
    with pytest.raises(ValueError):
        Router(enabled_registry(), max_active_agents=0)


async def test_guardrails_can_remove_candidates_and_the_removal_is_recorded() -> None:
    router = Router(
        enabled_registry("cardiology", "neurology"),
        [Fixed("a", cand("cardiology", reason=" "), cand("neurology", reason="ok"))],
        [RequireReasonGuardrail(), AllowedSpecialtiesGuardrail({"neurology"})],
    )
    decision = await router.route(INPUT)
    assert [s.specialist for s in decision.plan.selected] == ["neurology"]
    assert [n.name for n in decision.plan.not_selected] == ["cardiology"]
    assert any("guardrail require_reason" in line for line in decision.trace)


async def test_missing_information_from_strategies_is_reported_once() -> None:
    router = Router(
        enabled_registry(),
        [Fixed("a", missing=("age unknown",)), Fixed("b", missing=("age unknown", "no tests"))],
    )
    assert (await router.route(INPUT)).plan.missing_for_routing == ["age unknown", "no tests"]


async def test_a_failing_strategy_fails_routing_with_a_coded_error_and_no_content() -> None:
    class Boom:
        name = "boom"

        async def propose(self, routing_input: RouterInput) -> Proposal:
            raise RuntimeError("contains case text")

    with pytest.raises(RoutingError) as exc:
        await Router(enabled_registry(), [Boom()]).route(INPUT)
    assert exc.value.code == "strategy_failed" and "case text" not in str(exc.value)


async def test_the_rule_strategy_runs_whatever_rules_it_is_given_and_none_by_default() -> None:
    always = Rule("cardiology", "optional", "test rule", lambda i: True)
    never = Rule("neurology", "optional", "test rule", lambda i: False)
    assert list((await RuleStrategy([]).propose(INPUT)).candidates) == []
    proposal = await RuleStrategy([always, never]).propose(INPUT)
    assert [c.specialty for c in proposal.candidates] == ["cardiology"]


async def test_an_llm_assisted_strategy_is_validated_by_the_gateway_and_still_filtered_by_the_registry() -> (
    None
):
    class Proposer(LLMAssistedStrategy):
        def build_request(self, routing_input: RouterInput) -> GatewayRequest[RoutingProposal]:
            return GatewayRequest(
                schema=RoutingProposal, system="s", segments=[PromptSegment("synthetic", "free_text")]
            )

    reply = json.dumps(
        {
            "selections": [
                {"specialty": "cardiology", "priority": "optional", "reason": "r"},
                {"specialty": "neurology", "priority": "optional", "reason": "r"},
            ],
            "missing": ["m"],
        }
    )
    gateway, _provider, sink, _ = make_gateway(FakeProvider([FakeStep(text=reply)]))
    decision = await Router(enabled_registry("cardiology"), [Proposer(gateway)]).route(INPUT)
    assert [s.specialist for s in decision.plan.selected] == ["cardiology"]  # neurology is not enabled
    assert decision.plan.missing_for_routing == ["m"]
    assert sink.records[0].purpose == "router.propose"
