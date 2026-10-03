"""The shapes AI steps return (evidence, cross-review, routing plan, synthesis, questions, comparison) against
the frontend's Zod-built fixtures: the backend models accept exactly what the UI renders, round-trip it
unchanged, keep the wire snake_case and reject malformed variants. Fixtures are exported by
frontend/src/__tests__/fixtures/export-ai-shapes.test.ts (synthetic data only)."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas import WIRE_SHAPES
from tests.conftest import load_fixture, scenario_names

FILES: dict[str, tuple[str, bool]] = {
    # fixture file -> (WIRE_SHAPES key, is a list of documents)
    "evidence.json": ("evidence", False),
    "cross_review.json": ("cross_review", False),
    "routing_plan.json": ("routing_plan", False),
    "synthesis.json": ("synthesis", False),
    "questions.json": ("question", True),
    "comparison.json": ("comparison", False),
}
SCENARIOS = scenario_names()


def docs(scenario: str, filename: str) -> list[Any]:
    data = load_fixture(scenario, filename)
    return data if FILES[filename][1] else [data]


def model_for(filename: str) -> type[BaseModel]:
    return WIRE_SHAPES[FILES[filename][0]]


@pytest.mark.parametrize("filename", FILES)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_fixture_validates_and_round_trips(scenario: str, filename: str) -> None:
    model = model_for(filename)
    for doc in docs(scenario, filename):
        parsed = model.model_validate(doc)
        assert parsed.model_dump(mode="json") == doc
        assert model.model_validate_json(parsed.model_dump_json()).model_dump(mode="json") == doc


def _drop(path: list[str | int]) -> Callable[[Any], None]:
    def mutate(doc: Any) -> None:
        for step in path[:-1]:
            doc = doc[step]
        del doc[path[-1]]

    return mutate


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_a_synthesis_item_must_name_what_it_was_derived_from(scenario: str) -> None:
    doc = copy.deepcopy(load_fixture(scenario, "synthesis.json"))
    doc["items"][0]["derived_from"] = []
    with pytest.raises(ValidationError):
        model_for("synthesis.json").model_validate(doc)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_a_question_must_link_to_something(scenario: str) -> None:
    doc = copy.deepcopy(load_fixture(scenario, "questions.json")[0])
    doc["linked_item_ids"] = []
    with pytest.raises(ValidationError):
        model_for("questions.json").model_validate(doc)


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize(
    "filename", ["evidence.json", "cross_review.json", "routing_plan.json", "comparison.json"]
)
def test_unknown_and_null_fields_are_rejected(scenario: str, filename: str) -> None:
    model = model_for(filename)
    doc = copy.deepcopy(load_fixture(scenario, filename))
    with pytest.raises(ValidationError):
        model.model_validate({**doc, "surprise": 1})
    first_key = next(iter(doc))
    with pytest.raises(ValidationError):
        model.model_validate({**doc, first_key: None})


def test_the_comparison_contract_has_no_field_for_picking_a_winner() -> None:
    fields = set(model_for("comparison.json").model_fields) | {
        name for m in (WIRE_SHAPES["comparison"],) for name in m.model_fields
    }
    assert not fields & {"winner", "score", "preferred", "recommendation", "switch"}


def test_fixture_files_exist_for_every_scenario() -> None:
    for scenario in SCENARIOS:
        for filename in FILES:
            assert docs(scenario, filename), f"{scenario}/{filename} is empty"
    assert json.dumps(Path(__file__).name)  # keeps Path import used if the list above changes
