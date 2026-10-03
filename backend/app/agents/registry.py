"""Specialty registry: which agents exist, their metadata, and which are enabled. Config-driven
(`registry/agents.yaml`); an agent implementation is attached by whoever writes it."""

from pathlib import Path

import yaml

from app.agents.contracts import REQUIRED_SPECIALTIES, AgentSpec, SpecialtyAgent
from app.agents.prompts import PromptStore

DEFAULT_FILE = Path(__file__).resolve().parents[3] / "registry" / "agents.yaml"


class RegistryError(Exception):
    """Fixed-code error: agent_registry_invalid, agent_unknown, agent_duplicate, agent_disabled."""


class SpecialtyRegistry:
    def __init__(self, specs: list[AgentSpec]) -> None:
        self._specs: dict[str, AgentSpec] = {}
        for spec in specs:
            if spec.id in self._specs:
                raise RegistryError("agent_duplicate")
            self._specs[spec.id] = spec
        self._agents: dict[str, SpecialtyAgent] = {}

    @classmethod
    def from_file(cls, path: Path = DEFAULT_FILE) -> "SpecialtyRegistry":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            return cls([AgentSpec.model_validate(entry) for entry in raw["agents"]])
        except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as exc:
            raise RegistryError("agent_registry_invalid") from exc

    def spec(self, specialty: str) -> AgentSpec:
        try:
            return self._specs[specialty]
        except KeyError:
            raise RegistryError("agent_unknown") from None

    def specs(self) -> list[AgentSpec]:
        return list(self._specs.values())

    def is_enabled(self, specialty: str) -> bool:
        spec = self._specs.get(specialty)
        return bool(spec and spec.enabled)

    def enabled_ids(self) -> list[str]:
        return [s.id for s in self._specs.values() if s.enabled]

    def attach(self, agent: SpecialtyAgent) -> None:
        """Attach the implementation for a registered specialty."""
        self.spec(agent.spec.id)  # must be registered
        self._agents[agent.spec.id] = agent

    def agent(self, specialty: str) -> SpecialtyAgent:
        if not self.is_enabled(specialty):
            raise RegistryError("agent_disabled")
        try:
            return self._agents[specialty]
        except KeyError:
            raise RegistryError("agent_unknown") from None

    def readiness(self, prompts: PromptStore) -> dict[str, list[str]]:
        """What still blocks each REQUIRED specialty from running: missing from registry, disabled, no prompt
        written, no implementation attached. Empty list = ready."""
        report: dict[str, list[str]] = {}
        for sid in REQUIRED_SPECIALTIES:
            spec = self._specs.get(sid)
            if spec is None:
                report[sid] = ["not_registered"]
                continue
            blockers = []
            if not spec.enabled:
                blockers.append("disabled")
            if not prompts.is_written(sid, spec.prompt_version):
                blockers.append("prompt_not_written")
            if sid not in self._agents:
                blockers.append("no_implementation")
            report[sid] = blockers
        return report
