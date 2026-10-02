"""Workflow definitions: versioned YAML DAGs, validated on load (blueprint p. 9).

The workflow is DATA; the engine that runs it is swappable. A definition only names node TYPES and their
dependencies; which Python class implements a type is the node registry's business. A definition that
references a type nobody registered is refused when a run starts, never half-run.

    id: case_analysis
    version: 1
    nodes:
      - {id: classify, type: ai.classify_docs, retries: 2}
      - {id: extract,  type: ai.extract_facts, after: [classify], timeout_s: 120}

Rules: unique snake_case ids, `after` refers to existing nodes, no cycles, 1..14 nodes (`run.v1` shows at
most 14 steps), at most 2 retries (blueprint p. 38), a timeout on every node.
"""

import graphlib
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

MAX_NODES = 14
NodeId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
NodeType = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")]


class DefinitionError(Exception):
    """A definition file is invalid. The message names the file and the rule, never file content."""


class NodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NodeId
    type: NodeType
    after: list[NodeId] = Field(default_factory=list)
    retries: Annotated[int, Field(ge=0, le=2)] = 0
    timeout_s: Annotated[int, Field(ge=1, le=600)] = 60
    # A critical node that fails stops the run; a non-critical one makes the run `partial`.
    critical: bool = True
    # Model tier (blueprint p. 8). Carried for the later AI phase; nothing here reads it.
    tier: Annotated[int, Field(ge=1, le=3)] | None = None


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NodeId
    version: Annotated[int, Field(ge=1)]
    nodes: Annotated[list[NodeSpec], Field(min_length=1, max_length=MAX_NODES)]

    @model_validator(mode="after")
    def _valid_dag(self) -> Self:
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("node ids must be unique")
        known = set(ids)
        for node in self.nodes:
            missing = [a for a in node.after if a not in known]
            if missing:
                raise ValueError(f"node {node.id!r} depends on unknown node(s) {missing}")
            if node.id in node.after:
                raise ValueError(f"node {node.id!r} depends on itself")
        try:
            tuple(graphlib.TopologicalSorter({n.id: set(n.after) for n in self.nodes}).static_order())
        except graphlib.CycleError:
            raise ValueError("the workflow contains a cycle") from None
        return self

    def layers(self) -> list[list[NodeSpec]]:
        """Nodes grouped into layers that can run in parallel; within a layer, declaration order."""
        by_id = {n.id: n for n in self.nodes}
        order = {n.id: i for i, n in enumerate(self.nodes)}
        sorter = graphlib.TopologicalSorter({n.id: set(n.after) for n in self.nodes})
        sorter.prepare()
        out: list[list[NodeSpec]] = []
        while sorter.is_active():
            ready = sorted(sorter.get_ready(), key=order.__getitem__)
            out.append([by_id[i] for i in ready])
            sorter.done(*ready)
        return out

    def ordered_nodes(self) -> list[NodeSpec]:
        """The step order shown to people (`run.v1` step 1..N): layer by layer."""
        return [n for layer in self.layers() for n in layer]


def load_definition(path: Path) -> WorkflowDefinition:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return WorkflowDefinition.model_validate(raw)
    except (OSError, yaml.YAMLError) as exc:
        raise DefinitionError(f"{path.name}: could not be read ({type(exc).__name__})") from None
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise DefinitionError(f"{path.name}: {where}: {first['msg']}") from None


class DefinitionRegistry:
    """Definitions by (id, version). Old versions stay loadable so old runs stay reproducible."""

    def __init__(self, definitions: list[WorkflowDefinition] | None = None) -> None:
        self._by_key: dict[tuple[str, int], WorkflowDefinition] = {}
        for d in definitions or []:
            self.add(d)

    def add(self, definition: WorkflowDefinition) -> None:
        key = (definition.id, definition.version)
        if key in self._by_key:
            raise DefinitionError(f"duplicate workflow definition {definition.id}@{definition.version}")
        self._by_key[key] = definition

    def get(self, definition_id: str, version: int) -> WorkflowDefinition | None:
        return self._by_key.get((definition_id, version))

    def __len__(self) -> int:
        return len(self._by_key)

    @classmethod
    def from_directory(cls, directory: Path) -> "DefinitionRegistry":
        registry = cls()
        if directory.is_dir():
            for path in sorted(directory.glob("*.yaml")):
                registry.add(load_definition(path))
        return registry
