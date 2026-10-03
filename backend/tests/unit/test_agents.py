"""Specialty-agent contracts: registry, readiness, prompt store, and the deterministic report validator."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.contracts import REQUIRED_SPECIALTIES, AgentSpec, SpecialtyInput
from app.agents.prompts import PromptNotWrittenError, PromptStore
from app.agents.registry import RegistryError, SpecialtyRegistry
from app.agents.validate import errors, validate_specialist_report
from app.schemas import CaseV1, SpecialistReport
from app.schemas.common import ExternalSource

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def load(scenario: str) -> tuple[CaseV1, list[SpecialistReport], list[ExternalSource], dict[str, Any]]:
    case = CaseV1.model_validate(json.loads((FIX / scenario / "case.v1.json").read_text()))
    reports = [
        SpecialistReport.model_validate(r)
        for r in json.loads((FIX / scenario / "specialist_reports.v1.json").read_text())
    ]
    sources = [
        ExternalSource.model_validate(s)
        for s in json.loads((FIX / scenario / "evidence.json").read_text())["sources"]
    ]
    routing = json.loads((FIX / scenario / "routing_plan.json").read_text())
    return case, reports, sources, routing


def payload_for(report: SpecialistReport, scenario: str) -> tuple[SpecialtyInput, AgentSpec]:
    case, _, sources, routing = load(scenario)
    selected = routing["selected"]
    selection = next((s for s in selected if s["specialist"] == report.specialist), selected[0])
    payload = SpecialtyInput.model_validate(
        {
            "schema_version": "specialty_input.v1",
            "run_id": report.run_id,
            "case": case.model_dump(mode="json"),
            "routing": selection,
            "sources": [s.model_dump(mode="json") for s in sources],
        }
    )
    spec = AgentSpec(
        id=report.specialist,
        name=report.name,
        version=report.version,
        tier=report.tier,
        prompt_version=1,
        timeout_s=60,
        enabled=True,
    )
    return payload, spec


# ── registry ───────────────────────────────────────────────────────────────────────────────────────
def test_the_shipped_registry_has_the_five_specialties_all_disabled() -> None:
    registry = SpecialtyRegistry.from_file()
    assert [s.id for s in registry.specs()] == list(REQUIRED_SPECIALTIES)
    assert registry.enabled_ids() == []
    assert all(
        s.input_schema == "specialty_input.v1" and s.output_schema == "specialist_report.v1"
        for s in registry.specs()
    )


def test_readiness_lists_exactly_what_still_blocks_each_specialty() -> None:
    readiness = SpecialtyRegistry.from_file().readiness(PromptStore())
    assert set(readiness) == set(REQUIRED_SPECIALTIES)
    for blockers in readiness.values():
        assert blockers == ["disabled", "prompt_not_written", "no_implementation"]


def test_a_disabled_or_unknown_agent_cannot_be_fetched() -> None:
    registry = SpecialtyRegistry.from_file()
    with pytest.raises(RegistryError, match="agent_disabled"):
        registry.agent("cardiology")
    with pytest.raises(RegistryError, match="agent_unknown"):
        registry.spec("dermatology")


def test_duplicates_and_bad_files_are_rejected(tmp_path: Path) -> None:
    spec = SpecialtyRegistry.from_file().specs()[0]
    with pytest.raises(RegistryError, match="agent_duplicate"):
        SpecialtyRegistry([spec, spec])
    bad = tmp_path / "agents.yaml"
    bad.write_text("agents: [{id: nonsense}]")
    with pytest.raises(RegistryError, match="agent_registry_invalid"):
        SpecialtyRegistry.from_file(bad)


def test_an_implementation_can_be_attached_to_an_enabled_registered_specialty() -> None:
    registry = SpecialtyRegistry.from_file()
    enabled = registry.spec("cardiology").model_copy(update={"enabled": True})

    class Stub:
        spec = enabled

        async def run(self, payload: SpecialtyInput, context: object) -> SpecialistReport:
            raise NotImplementedError

    registry = SpecialtyRegistry([enabled, *[s for s in registry.specs() if s.id != "cardiology"]])
    registry.attach(Stub())
    assert registry.agent("cardiology").spec.id == "cardiology"
    assert registry.readiness(PromptStore())["cardiology"] == ["prompt_not_written"]


# ── prompts ────────────────────────────────────────────────────────────────────────────────────────
def test_placeholder_prompts_are_refused_until_they_are_written(tmp_path: Path) -> None:
    store = PromptStore()
    for sid in REQUIRED_SPECIALTIES:
        assert not store.is_written(sid, 1)
        with pytest.raises(PromptNotWrittenError, match="prompt_not_written"):
            store.get(sid, 1)
    with pytest.raises(PromptNotWrittenError, match="prompt_missing"):
        store.get("cardiology", 99)
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "v1.md").write_text("A real prompt.\n")
    prompt = PromptStore(tmp_path).get("x", 1)
    assert prompt.text == "A real prompt.\n" and len(prompt.sha256) == 64


# ── input / output contract ────────────────────────────────────────────────────────────────────────
def test_the_input_contract_is_strict_and_carries_no_identity_fields() -> None:
    _, reports, _, _ = load("cardiology")
    payload, _ = payload_for(reports[0], "cardiology")
    assert payload.schema_version == "specialty_input.v1"
    identity = {"name", "email", "phone", "address", "patient_name"}
    assert not identity & set(SpecialtyInput.model_fields)
    assert not identity & set(CaseV1.model_fields)
    with pytest.raises(ValidationError):
        SpecialtyInput.model_validate({**payload.model_dump(), "patient_name": "x"})


@pytest.mark.parametrize("scenario", ["cardiology", "missing_info", "conflicting"])
def test_fixture_reports_pass_the_validator_with_no_errors(scenario: str) -> None:
    _, reports, _, _ = load(scenario)
    for report in reports:
        payload, spec = payload_for(report, scenario)
        assert errors(validate_specialist_report(report, payload, spec)) == [], (scenario, report.specialist)


def test_each_contract_breach_is_caught_with_a_specific_code() -> None:
    _, reports, _, _ = load("cardiology")
    report = next(r for r in reports if r.specialist == "cardiology")
    payload, spec = payload_for(report, "cardiology")

    def codes(**changes: object) -> set[str]:
        mutated = report.model_copy(update=changes)
        return {v.code for v in validate_specialist_report(mutated, payload, spec)}

    first = report.findings[0]
    assert "specialist_mismatch" in codes(specialist="neurology")
    assert "case_mismatch" in codes(case_id="other") and "run_mismatch" in codes(run_id="other")
    assert "unknown_fact_ref" in codes(findings=[first.model_copy(update={"fact_refs": ["nope"]})])
    assert "patient_fact_untraced" in codes(
        findings=[first.model_copy(update={"kind": "patient_fact", "fact_refs": []})]
    )
    assert "external_evidence_unsourced" in codes(
        findings=[first.model_copy(update={"kind": "external_evidence", "source_ids": None})]
    )
    assert "unknown_source" in codes(
        findings=[first.model_copy(update={"kind": "external_evidence", "source_ids": ["ghost"]})]
    )
    assert "duplicate_id" in codes(findings=[first, first])
    assert "limitations_missing" in codes(limitations=[])
    assert "confidence_unexplained" in codes(confidence=report.confidence.model_copy(update={"reason": " "}))
    assert "status_note_missing" in codes(status="incomplete", status_note=None)
    assert "agent_metadata_mismatch" in codes(version="9.9.9")


def test_limitations_missing_is_a_warning_not_an_error() -> None:
    _, reports, _, _ = load("cardiology")
    report = reports[0].model_copy(update={"limitations": []})
    payload, spec = payload_for(reports[0], "cardiology")
    found = validate_specialist_report(report, payload, spec)
    assert [v.code for v in found] == ["limitations_missing"] and errors(found) == []
