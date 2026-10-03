"""Contract tests: the frontend's Zod-built fixtures against the backend's Pydantic models.

The fixtures in tests/fixtures/contracts/ are generated from the TypeScript mock scenarios by
`npm run export:fixtures` (frontend) and checked in. A frontend test fails if they drift from the
scenarios; these tests prove the backend accepts exactly what the frontend produces, round-trips it
unchanged, rejects malformed variants, and keeps the wire snake_case.
"""

import copy
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas import CONTRACTS, AnalysisRun, CaseV1, PatientReport, SpecialistReport, Trace
from tests.conftest import load_fixture, scenario_names

SCENARIOS = scenario_names()
SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
OPAQUE = {"extensions", "meta"}  # free-form content: its keys are data, not contract

# fixture file -> (model, is a list of documents)
FILES: dict[str, tuple[type[BaseModel], bool]] = {
    "case.v1.json": (CaseV1, False),
    "specialist_reports.v1.json": (SpecialistReport, True),
    "report.v1.json": (PatientReport, False),
    "traces.v1.json": (Trace, True),
    "run.v1.json": (AnalysisRun, False),
}


def documents(scenario: str, filename: str) -> list[Any]:
    data = load_fixture(scenario, filename)
    return data if FILES[filename][1] else [data]


def keys(value: Any, into: list[str] | None = None) -> list[str]:
    into = [] if into is None else into
    if isinstance(value, list):
        for v in value:
            keys(v, into)
    elif isinstance(value, dict):
        for k, v in value.items():
            into.append(k)
            if k not in OPAQUE:
                keys(v, into)
    return into


def test_the_three_synthetic_scenarios_are_present() -> None:
    assert SCENARIOS == ["cardiology", "conflicting", "missing_info"]
    for s in SCENARIOS:
        for filename in FILES:
            assert documents(s, filename), f"{s}/{filename} is empty"


@pytest.mark.parametrize("filename", FILES)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_fixture_validates_and_round_trips_unchanged(scenario: str, filename: str) -> None:
    model = FILES[filename][0]
    for doc in documents(scenario, filename):
        parsed = model.model_validate(doc)
        # What the backend would send equals what the frontend produced, byte for byte as data.
        assert parsed.model_dump(mode="json") == doc
        # ... and so does the JSON path used by real HTTP bodies.
        assert model.model_validate_json(parsed.model_dump_json()).model_dump(mode="json") == doc


@pytest.mark.parametrize("filename", FILES)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_wire_is_snake_case_throughout(scenario: str, filename: str) -> None:
    bad = sorted({k for doc in documents(scenario, filename) for k in keys(doc) if not SNAKE_CASE.match(k)})
    assert bad == []


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_cross_file_ids_line_up(scenario: str) -> None:
    case = CaseV1.model_validate(load_fixture(scenario, "case.v1.json"))
    run = AnalysisRun.model_validate(load_fixture(scenario, "run.v1.json"))
    report = PatientReport.model_validate(load_fixture(scenario, "report.v1.json"))
    reports = [
        SpecialistReport.model_validate(d) for d in load_fixture(scenario, "specialist_reports.v1.json")
    ]
    assert report.case_id == case.case_id == run.case_id
    assert report.run_id == run.id
    assert all(r.case_id == case.case_id and r.run_id == run.id for r in reports)


def test_schema_versions_match_the_frontend_zod_contracts() -> None:
    ts = (Path(__file__).parents[3] / "frontend" / "src" / "domain" / "schemas.ts").read_text(
        encoding="utf-8"
    )
    block = re.search(r"SCHEMA_VERSIONS = \{(.*?)\} as const", ts, re.S)
    assert block, "SCHEMA_VERSIONS not found in schemas.ts"
    frontend = set(re.findall(r'"([a-z_]+\.v\d+)"', block.group(1)))
    assert (
        frontend == set(CONTRACTS) == {"case.v1", "specialist_report.v1", "report.v1", "trace.v1", "run.v1"}
    )


# ── Malformed payload rejection ──────────────────────────────────────────────────────────────────
Mutation = Callable[[dict[str, Any]], object]


def doc(filename: str, index: int = 0) -> Any:
    return copy.deepcopy(documents("cardiology", filename)[index])


def reject(model: type[BaseModel], payload: Any) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("filename", FILES)
def test_a_missing_or_wrong_schema_version_is_rejected(filename: str) -> None:
    model = FILES[filename][0]
    missing = doc(filename)
    del missing["schema_version"]
    reject(model, missing)
    wrong = doc(filename)
    wrong["schema_version"] = wrong["schema_version"].replace(".v1", ".v2")
    reject(model, wrong)


@pytest.mark.parametrize("filename", FILES)
def test_an_unknown_top_level_key_is_rejected(filename: str) -> None:
    payload = doc(filename)
    payload["camelCaseLeak"] = 1
    reject(FILES[filename][0], payload)


def test_a_camel_case_key_in_place_of_its_snake_case_name_is_rejected() -> None:
    run = doc("run.v1.json")
    run["caseId"] = run.pop("case_id")
    reject(AnalysisRun, run)
    report = doc("report.v1.json")
    report["sections"][0]["items"][0]["evidenceIds"] = report["sections"][0]["items"][0].pop("evidence_ids")
    reject(PatientReport, report)


class TestCaseV1:
    def test_rejects_bad_demographics_and_coercion(self) -> None:
        for demographics in (
            {"age": -1, "sex": "M"},
            {"age": 121, "sex": "M"},
            {"age": 52, "sex": "Z"},
            {"age": "52", "sex": "M"},
        ):
            payload = doc("case.v1.json")
            payload["demographics"] = demographics
            reject(CaseV1, payload)

    def test_rejects_a_fact_without_a_fact_ref_and_a_bad_status(self) -> None:
        payload = doc("case.v1.json")
        payload["symptoms"][0]["fact_ref"] = ""
        reject(CaseV1, payload)
        payload = doc("case.v1.json")
        payload["diagnoses"][0]["status"] = "probable"
        reject(CaseV1, payload)

    def test_carries_no_identity_fields(self) -> None:
        text = str(doc("case.v1.json")).lower()
        for forbidden in ("owner_label", "email", "phone", "patient_name"):
            assert forbidden not in text
        reject(CaseV1, {**doc("case.v1.json"), "patient_name": "X"})


class TestSpecialistReport:
    @pytest.mark.parametrize(
        "field",
        [
            "run_id",
            "case_id",
            "missing_info",
            "questions",
            "evidence_refs",
            "findings",
            "uncertainties",
            "contradictions",
            "considerations",
            "confidence",
            "limitations",
            "specialist",
            "routing_reason",
        ],
    )
    def test_requires(self, field: str) -> None:
        payload = doc("specialist_reports.v1.json")
        del payload[field]
        reject(SpecialistReport, payload)

    def test_rejects_an_unknown_specialty_kind_and_tier(self) -> None:
        mutations: tuple[Mutation, ...] = (
            lambda p: p.update(specialist="Not A Specialty!"),
            lambda p: p["findings"][0].update(kind="opinion"),
            lambda p: p.update(tier=4),
            lambda p: p.update(status="great"),
        )
        for mutate in mutations:
            payload = doc("specialist_reports.v1.json")
            mutate(payload)
            reject(SpecialistReport, payload)

    def test_allows_specialty_extensions_with_free_form_keys(self) -> None:
        payload = doc("specialist_reports.v1.json")
        payload["extensions"] = {"cardiology": {"riskScoresMentioned": [], "any_key": 1}}
        parsed = SpecialistReport.model_validate(payload)
        assert parsed.model_dump(mode="json")["extensions"] == payload["extensions"]


class TestReport:
    def test_rejects_the_wrong_number_or_order_of_sections(self) -> None:
        payload = doc("report.v1.json")
        payload["sections"] = payload["sections"][:18]
        reject(PatientReport, payload)
        payload = doc("report.v1.json")
        payload["sections"][0], payload["sections"][1] = payload["sections"][1], payload["sections"][0]
        reject(PatientReport, payload)
        payload = doc("report.v1.json")
        payload["sections"].append(copy.deepcopy(payload["sections"][-1]))
        reject(PatientReport, payload)

    def test_rejects_a_claim_without_an_id_or_without_evidence(self) -> None:
        payload = doc("report.v1.json")
        item = next(i for s in payload["sections"] for i in s["items"] if i["kind"] != "template")
        without_id = copy.deepcopy(payload)
        next(i for s in without_id["sections"] for i in s["items"] if i["kind"] != "template").pop("id")
        reject(PatientReport, without_id)
        item["evidence_ids"] = []
        reject(PatientReport, payload)

    def test_allows_fixed_template_text_without_an_id(self) -> None:
        payload = doc("report.v1.json")
        payload["sections"][18]["items"] = [{"text": "Fixed notice", "kind": "template", "evidence_ids": []}]
        PatientReport.model_validate(payload)

    def test_rejects_a_bad_section_type_and_an_unparseable_date(self) -> None:
        payload = doc("report.v1.json")
        payload["sections"][0]["type"] = "essay"
        reject(PatientReport, payload)
        payload = doc("report.v1.json")
        payload["generated_at"] = "yesterday"
        reject(PatientReport, payload)


class TestTrace:
    def test_validates_nested_nodes_recursively(self) -> None:
        payload = doc("traces.v1.json")
        node = payload["root"]
        while node["children"]:
            node = node["children"][0]
        node["level"] = "nonsense"
        reject(Trace, payload)

    def test_rejects_a_source_with_a_non_positive_page(self) -> None:
        payload = next(
            d for d in documents("cardiology", "traces.v1.json") if '"source"' in str(d).replace("'", '"')
        )
        payload = copy.deepcopy(payload)

        def set_page(node: dict[str, Any]) -> bool:
            if "source" in node:
                node["source"]["page"] = 0
                return True
            return any(set_page(c) for c in node["children"])

        assert set_page(payload["root"])
        reject(Trace, payload)

    def test_children_are_required(self) -> None:
        payload = doc("traces.v1.json")
        del payload["root"]["children"]
        reject(Trace, payload)


class TestRun:
    def test_rejects_the_wrong_number_or_order_of_steps(self) -> None:
        payload = doc("run.v1.json")
        payload["steps"] = payload["steps"][:13]
        reject(AnalysisRun, payload)
        payload = doc("run.v1.json")
        payload["steps"][0], payload["steps"][1] = payload["steps"][1], payload["steps"][0]
        reject(AnalysisRun, payload)

    def test_a_failed_run_must_explain_itself(self) -> None:
        payload = doc("run.v1.json")
        payload["status"] = "failed"
        payload.pop("failure", None)
        reject(AnalysisRun, payload)
        payload["failure"] = {"title": "Stopped", "body": "Why"}
        AnalysisRun.model_validate(payload)

    def test_rejects_bad_progress_status_and_step_status(self) -> None:
        mutations: tuple[Mutation, ...] = (
            lambda p: p.update(progress=1.5),
            lambda p: p.update(progress=-0.1),
            lambda p: p.update(status="exploded"),
            lambda p: p["steps"][0].update(status="finished"),
            lambda p: p.update(progress="done"),
        )
        for mutate in mutations:
            payload = doc("run.v1.json")
            mutate(payload)
            reject(AnalysisRun, payload)
