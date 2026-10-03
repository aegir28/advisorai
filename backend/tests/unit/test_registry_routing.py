"""Registry v2 and config-driven routing: specialists are data, the router names none of them."""

import json
from pathlib import Path

import pytest

from app.agents.contracts import AgentSpec, Trigger
from app.agents.registry import RegistryError, SpecialtyRegistry
from app.router.contracts import RouterInput
from app.router.router import Router
from app.router.signals import CaseSignals, SignalConfigError, SignalExtractor
from app.router.strategies import RegistryRuleStrategy
from app.schemas import CaseV1

pytestmark = pytest.mark.anyio

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def case(scenario: str) -> CaseV1:
    return CaseV1.model_validate(json.loads((FIX / scenario / "case.v1.json").read_text()))


def enabled(registry: SpecialtyRegistry, *ids: str) -> SpecialtyRegistry:
    wanted = set(ids) or {s.id for s in registry.specs()}
    return SpecialtyRegistry([s.model_copy(update={"enabled": s.id in wanted}) for s in registry.specs()])


def spec(agent_id: str, **kw: object) -> AgentSpec:
    base: dict[str, object] = {
        "id": agent_id,
        "name": agent_id.title(),
        "version": "0.1.0",
        "tier": 2,
        "prompt_version": 1,
        "timeout_s": 60,
        "enabled": True,
        "prompt_mode": "shared",
        "focus": "Looks at one area.",
    }
    return AgentSpec.model_validate(base | kw)


# ── signals ────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("scenario", "present", "absent"),
    [
        (
            "cardiology",
            {"always", "medications_present", "cardiac", "cardiac_procedure_proposed"},
            {"neurological"},
        ),
        ("missing_info", {"musculoskeletal", "medications_present"}, {"cardiac", "neurological"}),
        ("conflicting", {"neurological", "medications_present"}, {"cardiac", "musculoskeletal"}),
    ],
)
def test_signals_come_from_the_structured_case(scenario: str, present: set[str], absent: set[str]) -> None:
    signals = SignalExtractor.from_file().extract(case(scenario))
    assert present <= set(signals.names())
    assert not absent & set(signals.names())


def test_a_signal_carries_counts_and_field_names_never_case_text() -> None:
    signals = SignalExtractor.from_file().extract(case("cardiology"))
    hit = signals.hits["cardiac"]
    assert hit.matches >= 1 and set(hit.fields) <= {
        "symptoms",
        "diagnoses",
        "investigations",
        "procedures",
        "history",
        "recommendations",
        "proposed",
        "chief_concern",
        "treatment_history",
        "surgeries",
    }
    assert not hasattr(hit, "terms")


def test_bad_signal_files_are_refused(tmp_path: Path) -> None:
    for text in (
        "version: 2\nfields: []\nsignals: {}",
        "version: 1\nfields: [symptoms]\nsignals: {always: {terms: [x]}}",
        "nonsense: [",
    ):
        f = tmp_path / "s.yaml"
        f.write_text(text)
        with pytest.raises(SignalConfigError, match="signals_config_invalid"):
            SignalExtractor.from_file(f)


# ── registry v2 ─────────────────────────────────────────────────────────────────────────────────────
def test_the_hierarchy_is_validated() -> None:
    parent = spec("cardiology", kind="specialty")
    SpecialtyRegistry([parent, spec("electrophysiology", kind="subspecialty", parent="cardiology")])
    for bad in (
        [spec("electrophysiology", kind="subspecialty", parent="nobody")],
        [parent, spec("electrophysiology", kind="subspecialty")],
        [
            parent,
            spec("heart_failure", kind="subspecialty", parent="electrophysiology"),
            spec("electrophysiology", kind="subspecialty", parent="cardiology"),
        ],
        [parent, spec("other_one", kind="specialty", parent="cardiology")],
        [spec("no_focus", focus="")],
    ):
        with pytest.raises(RegistryError):
            SpecialtyRegistry(bad)


def test_an_agent_id_is_an_identifier_not_a_closed_list() -> None:
    for bad in ("Cardiology", "x", "has space", "1abc", "a" * 70):
        with pytest.raises(ValueError):
            spec(bad)
    assert spec("pediatric_cardiology").id == "pediatric_cardiology"


# ── config-driven routing ───────────────────────────────────────────────────────────────────────────
async def route(registry: SpecialtyRegistry, c: CaseV1, cap: int = 10):  # type: ignore[no-untyped-def]
    router = Router(
        registry, [RegistryRuleStrategy(registry, SignalExtractor.from_file())], max_active_agents=cap
    )
    return await router.route(RouterInput(case=c))


async def test_shipped_triggers_select_perspectives_from_the_case() -> None:
    decision = await route(enabled(SpecialtyRegistry.from_file()), case("cardiology"))
    chosen = {s.specialist: s.priority for s in decision.plan.selected}
    assert chosen["general_medicine"] == "mandatory" and chosen["medication_safety"] == "mandatory"
    assert chosen["cardiology"] == "mandatory" and chosen["interventional_cardiology"] == "optional"
    assert "neurology" not in chosen and "orthopedics" not in chosen and "oncology" not in chosen


async def test_a_disabled_agent_is_never_selected() -> None:
    decision = await route(enabled(SpecialtyRegistry.from_file(), "general_medicine"), case("cardiology"))
    assert [s.specialist for s in decision.plan.selected] == ["general_medicine"]


async def test_reasons_and_trace_are_content_free() -> None:
    c = case("cardiology")
    decision = await route(enabled(SpecialtyRegistry.from_file()), c)
    blob = json.dumps(decision.plan.model_dump()) + " ".join(decision.trace)
    for word in ("troponin", "angioplasty", "LAD", "diclofenac", "metformin"):
        assert word.lower() not in blob.lower()
    cardiology = next(s for s in decision.plan.selected if s.specialist == "cardiology")
    assert "matching mention" in cardiology.reason


async def test_hundreds_of_specialists_need_no_workflow_or_router_change() -> None:
    """A registry of 300 specialties: only the ones whose trigger fires are selected; the router is unchanged."""
    agents = [
        spec(
            "general_medicine",
            triggers=[Trigger(signal="always", priority="mandatory", reason="Broad view.")],
        )
    ]
    for i in range(299):
        signal = "cardiac" if i % 3 == 0 else "oncological" if i % 3 == 1 else "neurological"
        agents.append(
            spec(
                f"specialist_{i:03d}",
                triggers=[Trigger(signal=signal, priority="optional", reason="Relevant.")],
            )
        )
    registry = SpecialtyRegistry(agents)
    assert len(registry.specs()) == 300
    decision = await route(registry, case("cardiology"), cap=12)
    selected = [s.specialist for s in decision.plan.selected]
    assert selected[0] == "general_medicine" and len(selected) == 12  # capped, mandatory first
    assert all(int(a.split("_")[1]) % 3 == 0 for a in selected[1:])  # only the cardiac ones
    assert any(n.why == "active-agent limit reached" for n in decision.plan.not_selected)


async def test_routing_reports_a_case_with_nothing_to_route_on() -> None:
    c = case("cardiology").model_copy(update={"symptoms": [], "medications": []})
    decision = await route(enabled(SpecialtyRegistry.from_file()), c)
    assert decision.plan.missing_for_routing


def test_case_signals_is_a_plain_value() -> None:
    assert CaseSignals({}).names() == [] and not CaseSignals({}).has("always")
