"""Orchestration policy: from `registry/orchestration.yaml`, validated, and handed to n8n at run start."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_FILE = Path(__file__).resolve().parents[3] / "registry" / "orchestration.yaml"


class PolicyError(Exception):
    """orchestration_policy_invalid. The message is a fixed code."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Limits(_Strict):
    max_active_agents: Annotated[int, Field(ge=1, le=50)]
    max_parallel_agents: Annotated[int, Field(ge=1, le=20)]
    min_specialists_for_cross_review: Annotated[int, Field(ge=1, le=10)]
    max_documents: Annotated[int, Field(ge=1, le=100)]


class Escalation(_Strict):
    tier: Literal[2, 3]
    if_disagreements_at_least: Annotated[int, Field(ge=1)]


class Conditions(_Strict):
    extra_verification_if_contradicted_at_least: Annotated[int, Field(ge=1)]
    missing_info_branch_if_evidence_items_below: Annotated[int, Field(ge=0)]
    verification_model_enabled: bool
    review_escalation: Escalation


class Retry(_Strict):
    stage_retries: Annotated[int, Field(ge=0, le=3)]
    backoff_seconds: Annotated[int, Field(ge=0, le=120)]


class Timeouts(_Strict):
    stage_seconds: Annotated[int, Field(ge=10, le=900)]
    agent_seconds: Annotated[int, Field(ge=10, le=600)]


class OrchestrationPolicy(_Strict):
    version: Literal[1]
    limits: Limits
    conditions: Conditions
    retry: Retry
    timeouts: Timeouts

    @classmethod
    def from_file(cls, path: Path = DEFAULT_FILE) -> "OrchestrationPolicy":
        try:
            return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError, ValidationError, TypeError) as exc:
            raise PolicyError("orchestration_policy_invalid") from exc
