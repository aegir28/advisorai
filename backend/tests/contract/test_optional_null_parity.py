"""Zod <-> Pydantic parity for field shape and optional/null semantics.

Zod `.optional()` accepts an ABSENT key and rejects `null`. The Pydantic models must behave
identically, so for every optional field of every versioned contract:

* absent  -> accepted
* null    -> rejected

`tests/fixtures/contracts/contract-shapes.json` is generated from the Zod schemas
(`npm run export:fixtures`): the exact set of field paths and which are optional. These tests
compare it with the Pydantic models, so a field or optionality drift in either direction fails.
"""

import copy
import json
import types
from typing import Annotated, Any, Union, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

import app.api.health
import app.schemas  # noqa: F401  (imports every model so subclasses are registered)
from app.schemas import CONTRACTS
from app.schemas.common import WireModel
from tests.conftest import FIXTURES, load_fixture, scenario_names

SHAPES: dict[str, dict[str, list[str]]] = json.loads(
    (FIXTURES / "contract-shapes.json").read_text(encoding="utf-8")
)

# schema_version -> fixture file (documents are lists for specialist reports and traces)
FIXTURE_FILE = {
    "case.v1": "case.v1.json",
    "specialist_report.v1": "specialist_reports.v1.json",
    "report.v1": "report.v1.json",
    "trace.v1": "traces.v1.json",
    "run.v1": "run.v1.json",
}


# ── Pydantic side: the same path syntax the Zod export uses ──────────────────────────────────────
def _unwrap(annotation: Any) -> Any:
    """Strip Annotated[...] and `X | None`, returning the inner type."""
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
        elif origin in (Union, types.UnionType):
            inner = [a for a in get_args(annotation) if a is not type(None)]
            if len(inner) != 1:
                return annotation
            annotation = inner[0]
        else:
            return annotation


def pydantic_shape(model: type[BaseModel]) -> tuple[set[str], set[str]]:
    fields: set[str] = set()
    optional: set[str] = set()

    def walk(cls: type[BaseModel], path: str, stack: tuple[type[BaseModel], ...]) -> None:
        if cls in stack:  # recursion (trace children): stop at the first repeat, as the Zod side does
            return
        for name, field in cls.model_fields.items():
            field_path = f"{path}.{name}" if path else name
            fields.add(field_path)
            if not field.is_required():
                optional.add(field_path)
            inner = _unwrap(field.annotation)
            suffix = ""
            while get_origin(inner) is list:
                suffix += "[]"
                inner = _unwrap(get_args(inner)[0])
            if isinstance(inner, type) and issubclass(inner, WireModel):
                walk(inner, field_path + suffix, (*stack, cls))
            # dict (free-form `extensions` / `meta`), scalars, literals: leaves

    walk(model, "", ())
    return fields, optional


@pytest.mark.parametrize("version", sorted(CONTRACTS))
def test_field_paths_and_optionality_match_the_zod_contract(version: str) -> None:
    fields, optional = pydantic_shape(CONTRACTS[version])
    zod_fields, zod_optional = set(SHAPES[version]["fields"]), set(SHAPES[version]["optional"])
    assert fields == zod_fields, (
        f"only in pydantic: {sorted(fields - zod_fields)}; only in zod: {sorted(zod_fields - fields)}"
    )
    assert optional == zod_optional, (
        f"optional only in pydantic: {sorted(optional - zod_optional)}; only in zod: {sorted(zod_optional - optional)}"
    )


def test_every_versioned_contract_has_a_shape() -> None:
    assert sorted(SHAPES) == sorted(CONTRACTS) == sorted(FIXTURE_FILE)


# ── Behaviour: absent accepted, explicit null rejected, for EVERY optional path ──────────────────
def _parse(path: str) -> list[tuple[str, bool]]:
    """'a.b[].c' -> [('a', False), ('b', True), ('c', False)]; True = the value is a list to fan out."""
    steps: list[tuple[str, bool]] = []
    for part in path.split("."):
        steps.append((part.removesuffix("[]"), part.endswith("[]")))
    return steps


def _apply(node: Any, steps: list[tuple[str, bool]], action: str) -> bool:
    """Walk `node` along `steps`; at the last step set the key to None ('null') or delete it ('absent').

    Returns True if it was applied at least once.
    """
    key, is_list = steps[0]
    if not isinstance(node, dict):
        return False
    if len(steps) == 1:
        if action == "null":
            node[key] = None
        else:
            node.pop(key, None)
        return True
    child = node.get(key)
    if child is None:
        return False
    children = child if is_list else [child]
    return any([_apply(c, steps[1:], action) for c in children])


def _documents(version: str) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for scenario in scenario_names():
        data = load_fixture(scenario, FIXTURE_FILE[version])
        for index, doc in enumerate(data if isinstance(data, list) else [data]):
            out.append((f"{scenario}[{index}]", doc))
    if version == "case.v1":
        # No scenario has pathology results. `pathology` items are the same `InvestigationItem` type
        # as `labs`, so mirror a populated labs list to exercise those paths (the fixtures and the
        # data model are left untouched).
        synthetic = copy.deepcopy(out[0][1])
        synthetic["investigations"]["pathology"] = copy.deepcopy(synthetic["investigations"]["labs"])
        out.append(("synthetic: pathology mirrors labs", synthetic))
    return out


# `id` is optional only for fixed template text: dropping it from a claim is (correctly) invalid, so
# the "absent is accepted" half is covered by test_template_text_may_omit_its_id instead.
CONDITIONALLY_REQUIRED = {("report.v1", "sections[].items[].id")}

CASES = [(version, path) for version in sorted(SHAPES) for path in SHAPES[version]["optional"]]


@pytest.mark.parametrize(("version", "path"), CASES, ids=[f"{v}:{p}" for v, p in CASES])
def test_optional_field_is_accepted_when_absent_and_rejected_when_null(version: str, path: str) -> None:
    model = CONTRACTS[version]
    steps = _parse(path)
    exercised = False
    for _label, doc in _documents(version):
        model.model_validate(doc)  # baseline is valid

        with_null = copy.deepcopy(doc)
        if not _apply(with_null, steps, "null"):
            continue  # this document has no object at that path
        exercised = True
        with pytest.raises(ValidationError, match="null is not allowed"):
            model.model_validate(with_null)

        if (version, path) not in CONDITIONALLY_REQUIRED:
            absent = copy.deepcopy(doc)
            _apply(absent, steps, "absent")
            model.model_validate(absent)
        break
    assert exercised, f"no fixture contains an object at `{path}`; add one so null handling is exercised"


# ── The rule holds for every model, including ones no fixture reaches ────────────────────────────
def _all_wire_models() -> list[type[WireModel]]:
    seen: list[type[WireModel]] = []
    stack: list[type[WireModel]] = [WireModel]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub not in seen:
                seen.append(sub)
                stack.append(sub)
    return seen


@pytest.mark.parametrize("cls", _all_wire_models(), ids=lambda c: c.__name__)
def test_no_wire_model_accepts_an_explicit_null_for_a_declared_field(cls: type[WireModel]) -> None:
    for name in cls.model_fields:
        with pytest.raises(ValidationError) as caught:
            cls.model_validate({name: None})
        assert any(
            e["loc"] == () and f"null is not allowed for {name}" in e["msg"] for e in caught.value.errors()
        ), f"{cls.__name__}.{name} did not reject null explicitly"


def test_free_form_content_may_still_hold_nulls() -> None:
    """`extensions` is data, not contract: Zod's z.unknown() allows null inside it."""
    doc = copy.deepcopy(_documents("specialist_report.v1")[0][1])
    doc["extensions"] = {"cardiology": {"score": None}}
    assert CONTRACTS["specialist_report.v1"].model_validate(doc).model_dump(mode="json")["extensions"] == {
        "cardiology": {"score": None}
    }


def test_the_json_schemas_never_advertise_null() -> None:
    def has_null_type(node: Any) -> bool:
        if isinstance(node, dict):
            return node.get("type") == "null" or any(has_null_type(v) for v in node.values())
        if isinstance(node, list):
            return any(has_null_type(v) for v in node)
        return False

    for version, model in CONTRACTS.items():
        assert not has_null_type(model.model_json_schema()), f"{version} advertises null"
    # ... while an optional field is still just "not required"
    schema = CONTRACTS["run.v1"].model_json_schema()
    assert "failure" in schema["properties"] and "failure" not in schema["required"]


def test_template_text_may_omit_its_id_but_never_send_it_as_null() -> None:
    report = CONTRACTS["report.v1"]
    doc = copy.deepcopy(_documents("report.v1")[0][1])
    doc["sections"][18]["items"] = [{"text": "Fixed notice", "kind": "template", "evidence_ids": []}]
    report.model_validate(doc)  # id absent: accepted
    doc["sections"][18]["items"][0]["id"] = None
    with pytest.raises(ValidationError, match="null is not allowed"):
        report.model_validate(doc)
