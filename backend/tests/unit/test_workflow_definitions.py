"""Workflow definitions: valid DAGs load, every invalid shape is refused with a message that never echoes content."""

from pathlib import Path

import pytest

from app.workflow.definitions import (
    MAX_NODES,
    DefinitionError,
    DefinitionRegistry,
    WorkflowDefinition,
    load_definition,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "workflows"


def make(nodes: list[dict[str, object]], *, id_: str = "wf", version: int = 1) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate({"id": id_, "version": version, "nodes": nodes})


def node(i: str, *after: str, **extra: object) -> dict[str, object]:
    return {"id": i, "type": "test.noop", "after": list(after), **extra}


def test_the_fixture_definition_loads_with_four_layers_and_14_steps() -> None:
    d = load_definition(FIXTURES / "foundation_smoke.v1.yaml")
    assert (d.id, d.version, len(d.nodes)) == ("foundation_smoke", 1, 14)
    assert [len(layer) for layer in d.layers()] == [1, 4, 4, 4, 1]
    assert [n.id for n in d.ordered_nodes()][:3] == ["n01", "n02", "n03"]
    assert d.nodes[5].retries == 1 and d.nodes[9].critical is False


def test_layers_respect_dependencies_and_declaration_order() -> None:
    d = make([node("c", "a", "b"), node("b"), node("a")])
    assert [[n.id for n in layer] for layer in d.layers()] == [["b", "a"], ["c"]]


@pytest.mark.parametrize(
    ("nodes", "fragment"),
    [
        ([node("a"), node("a")], "unique"),
        ([node("a", "ghost")], "unknown node"),
        ([node("a", "a")], "itself"),
        ([node("a", "b"), node("b", "a")], "cycle"),
        ([node("a", retries=3)], "retries"),
        ([node("a", timeout_s=0)], "timeout"),
        ([node("A")], "id"),
        ([{"id": "a", "type": "noop"}], "type"),
        ([node("a", surprise=1)], "surprise"),
        ([], "nodes"),
        ([node(f"n{i:02d}") for i in range(MAX_NODES + 1)], "nodes"),
    ],
)
def test_invalid_definitions_are_refused(nodes: list[dict[str, object]], fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        make(nodes)


def test_the_registry_keeps_old_versions_and_refuses_duplicates() -> None:
    v1, v2 = make([node("a")], version=1), make([node("a")], version=2)
    registry = DefinitionRegistry([v1, v2])
    assert registry.get("wf", 1) is v1 and registry.get("wf", 2) is v2 and registry.get("wf", 3) is None
    with pytest.raises(DefinitionError, match="duplicate"):
        registry.add(v1)


def test_a_broken_file_names_the_problem_not_its_content(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: wf\nversion: 1\nnodes:\n  - {id: a, type: test.noop, after: [PATIENT-SECRET]}\n")
    with pytest.raises(DefinitionError) as info:
        load_definition(bad)
    assert "bad.yaml" in str(info.value)
    broken = tmp_path / "broken.yaml"
    broken.write_text("id: [unclosed\n")
    with pytest.raises(DefinitionError, match=r"broken\.yaml"):
        load_definition(broken)
    with pytest.raises(DefinitionError, match=r"missing\.yaml"):
        load_definition(tmp_path / "missing.yaml")


def test_a_directory_loads_every_yaml_and_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert len(DefinitionRegistry.from_directory(FIXTURES)) == 1
    assert len(DefinitionRegistry.from_directory(tmp_path / "nope")) == 0
