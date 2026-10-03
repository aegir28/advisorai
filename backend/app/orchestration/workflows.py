"""Workflow definitions: the stage graph of a run, loaded from `registry/workflows.yaml` and validated.

Nothing here (or in n8n) knows which stages exist. A definition is a list of stages with a kind (single |
fanout), a handler name, criticality, an optional `when` flag, declared flags, dependencies and optional retry /
timeout overrides. The service creates a run's steps from the selected definition, `begin` returns descriptors,
and the n8n master executes whatever it is given.
"""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.orchestration.policy import OrchestrationPolicy

DEFAULT_FILE = Path(__file__).resolve().parents[3] / "registry" / "workflows.yaml"
MAX_STAGES = 64
_ID = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
_FLAG = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
StageKind = Literal["single", "fanout"]
Param = str | int | bool


class WorkflowConfigError(Exception):
    """workflow_config_invalid. The message is a fixed code, optionally `code:detail` (never case content)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StageDef(_Strict):
    id: str
    kind: StageKind
    handler: str
    critical: bool
    uses_model: bool = False
    when: str | None = None
    flags: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    retries: Annotated[int, Field(ge=0, le=5)] | None = None
    backoff_seconds: Annotated[int, Field(ge=0, le=300)] | None = None
    timeout_seconds: Annotated[int, Field(ge=10, le=900)] | None = None
    params: Mapping[str, Param] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _names(self) -> Self:
        if not _ID.match(self.id) or not _ID.match(self.handler):
            raise ValueError("bad_stage_name")
        if any(not _FLAG.match(f) for f in (*self.flags, *([self.when] if self.when else []))):
            raise ValueError("bad_flag_name")
        return self


class WorkflowDef(_Strict):
    id: str = ""
    version: Annotated[int, Field(ge=1)]
    description: str = ""
    stages: tuple[StageDef, ...]

    @model_validator(mode="after")
    def _graph(self) -> Self:
        if not 1 <= len(self.stages) <= MAX_STAGES:
            raise ValueError("stage_count")
        seen: set[str] = set()
        declared: set[str] = set()
        for stage in self.stages:
            if stage.id in seen:
                raise ValueError(f"duplicate_stage:{stage.id}")
            for dep in stage.depends_on:
                if dep not in seen:
                    raise ValueError(f"dependency_not_earlier:{stage.id}")
            if stage.when is not None and stage.when not in declared:
                raise ValueError(f"when_flag_not_declared_earlier:{stage.id}")
            seen.add(stage.id)
            declared.update(stage.flags)
        return self

    @property
    def stage_ids(self) -> list[str]:
        return [s.id for s in self.stages]

    def stage(self, stage_id: str) -> StageDef:
        for s in self.stages:
            if s.id == stage_id:
                return s
        raise KeyError("unknown_stage")

    def number(self, stage_id: str) -> int:
        """The 1-based step number of a stage (the `n` of run.v1)."""
        return self.stage_ids.index(stage_id) + 1


class WorkflowRegistry:
    def __init__(self, workflows: Mapping[str, WorkflowDef]) -> None:
        if not workflows:
            raise WorkflowConfigError("workflow_config_invalid")
        self._workflows = dict(workflows)

    @classmethod
    def from_file(cls, path: Path = DEFAULT_FILE) -> "WorkflowRegistry":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if raw.get("version") != 1:
                raise WorkflowConfigError("workflow_config_invalid")
            return cls.from_dict(raw["workflows"])
        except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError) as exc:
            raise WorkflowConfigError("workflow_config_invalid") from exc

    @classmethod
    def from_dict(cls, workflows: Mapping[str, object]) -> "WorkflowRegistry":
        out: dict[str, WorkflowDef] = {}
        for wf_id, body in workflows.items():
            if not _ID.match(str(wf_id)) or not isinstance(body, dict):
                raise WorkflowConfigError("workflow_config_invalid")
            try:
                out[wf_id] = WorkflowDef.model_validate({**body, "id": wf_id})
            except ValidationError as exc:
                detail = str(exc.errors()[0].get("msg", "invalid")).removeprefix("Value error, ")
                raise WorkflowConfigError(f"workflow_config_invalid:{wf_id}:{detail}") from exc
        return cls(out)

    def ids(self) -> list[str]:
        return list(self._workflows)

    def get(self, workflow_id: str) -> WorkflowDef:
        try:
            return self._workflows[workflow_id]
        except KeyError:
            raise WorkflowConfigError("workflow_unknown") from None

    def check_handlers(self, available: Mapping[str, Iterable[StageKind]]) -> None:
        """Every stage names a handler that exists and supports the stage's kind."""
        for wf in self._workflows.values():
            for stage in wf.stages:
                if stage.handler not in available:
                    raise WorkflowConfigError(f"handler_unknown:{wf.id}:{stage.id}")
                if stage.kind not in set(available[stage.handler]):
                    raise WorkflowConfigError(f"handler_kind_mismatch:{wf.id}:{stage.id}")


def resolved(stage: StageDef, policy: OrchestrationPolicy) -> tuple[int, int, int]:
    """(retries, backoff seconds, timeout seconds): the stage's override or the policy default."""
    return (
        stage.retries if stage.retries is not None else policy.retry.stage_retries,
        stage.backoff_seconds if stage.backoff_seconds is not None else policy.retry.backoff_seconds,
        stage.timeout_seconds if stage.timeout_seconds is not None else policy.timeouts.stage_seconds,
    )
