"""run.v1: status and steps of one analysis run (never its content)."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .common import Id, IsoDate, WireModel

RUN_SCHEMA_VERSION = "run.v1"
# A run's steps come from its workflow definition (registry/workflows.yaml), so the count varies; the bound
# matches the loader's maximum and the database check. `case_analysis` still has 14 steps.
MAX_STEPS = 64

StepStatus = Literal["pending", "running", "done", "warning", "failed", "skipped"]
RunStatus = Literal["running", "complete", "partial", "failed"]


class RunStep(WireModel):
    # 1..N in workflow order; the patient-facing title is a frontend concern.
    n: Annotated[int, Field(ge=1, le=MAX_STEPS)]
    status: StepStatus
    note: str | None = None


class RunFailure(WireModel):
    title: str
    body: str


class AnalysisRun(WireModel):
    schema_version: Literal["run.v1"]
    id: Id
    case_id: Id
    status: RunStatus
    progress: Annotated[float, Field(ge=0, le=1)]
    steps: list[RunStep]
    started_at: IsoDate
    finished_at: IsoDate | None = None
    # Present when a critical failure stops the run.
    failure: RunFailure | None = None
    # Present when the run finished with gaps.
    warnings: list[str]

    @model_validator(mode="after")
    def _steps_and_failure_are_consistent(self) -> Self:
        if not self.steps or [s.n for s in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("a run has at least one step, numbered 1..N in order")
        if self.status == "failed" and self.failure is None:
            raise ValueError("a failed run must explain itself in `failure`")
        return self
