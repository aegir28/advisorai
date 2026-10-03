"""Model registry: tier -> concrete model per provider, with prices. Loaded from `registry/models.yaml`.

The registry refuses rather than guesses: an unknown tier, a disabled model or a placeholder id raises
`GatewayError("model_not_configured")`. Money is integer micro-USD (1 USD = 1_000_000).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import yaml

from app.ai.types import AIConfigError, GatewayError, Usage

PLACEHOLDER_PREFIX = "REPLACE_ME"
MICROS = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class ModelSpec:
    id: str
    provider: str
    tier: int
    enabled: bool
    priced: bool
    input_per_mtok_usd: Decimal
    output_per_mtok_usd: Decimal
    max_output_tokens: int

    def cost_micro_usd(self, usage: Usage) -> int | None:
        """Integer micro-USD for this usage, or None when the model has no price entered yet."""
        if not self.priced:
            return None
        usd = (
            Decimal(usage.input_tokens) * self.input_per_mtok_usd
            + Decimal(usage.output_tokens) * self.output_per_mtok_usd
        ) / MICROS
        return int((usd * MICROS).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# What we KNOW about a provider data handling. Never "verified" on a document say-so: `verified` means the
# project holds a confirmation (an approved zero-retention agreement, or equivalent). `requestable` means the
# provider's official documentation says it is available on approval and we do not hold it yet.
RETENTION_STATES = ("verified", "requestable", "unverified", "unsuitable", "not_applicable")
PRIVACY_POLICIES = ("allow_unverified_synthetic", "require_verified")


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    name: str
    zero_retention: str = "unverified"
    source: str = ""
    checked_on: str = ""
    notes: str = ""

    def allowed_under(self, policy: str) -> bool:
        """`allow_unverified_synthetic` (the prototype default, legitimate only because the data is
        synthetic) refuses just `unsuitable`; `require_verified` also refuses everything not verified."""
        if self.zero_retention == "unsuitable":
            return False
        if policy == "require_verified":
            return self.zero_retention in ("verified", "not_applicable")
        return True


@dataclass(frozen=True, slots=True)
class ChainEntry:
    """One candidate in a task's ordered fallback chain: a provider tier, or an explicit model id."""

    provider: str | None = None
    tier: int | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    provider: str
    spec: "ModelSpec"


class ModelRegistry:
    def __init__(
        self,
        models: dict[str, ModelSpec],
        routes: dict[str, dict[int, str]],
        *,
        providers: dict[str, ProviderPolicy] | None = None,
        tasks: dict[str, list[ChainEntry]] | None = None,
    ) -> None:
        self._models = models
        self._routes = routes
        self._providers = providers or {}
        self._tasks = tasks or {}

    @classmethod
    def from_file(cls, path: Path) -> "ModelRegistry":
        try:
            raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise AIConfigError("model_registry_unreadable") from exc
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ModelRegistry":
        try:
            models = {
                str(mid): ModelSpec(
                    id=str(mid),
                    provider=str(spec["provider"]),
                    tier=0,
                    enabled=bool(spec["enabled"]),
                    priced=bool(spec["priced"]),
                    input_per_mtok_usd=Decimal(str(spec["input_per_mtok_usd"])),
                    output_per_mtok_usd=Decimal(str(spec["output_per_mtok_usd"])),
                    max_output_tokens=int(spec["max_output_tokens"]),
                )
                for mid, spec in raw["models"].items()
            }
            routes = {
                str(provider): {int(tier): str(mid) for tier, mid in tiers.items()}
                for provider, tiers in raw["routes"].items()
            }
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise AIConfigError("model_registry_invalid") from exc
        for provider, tiers in routes.items():
            for tier, mid in tiers.items():
                if mid not in models:
                    raise AIConfigError("model_registry_invalid")
                if models[mid].provider != provider:
                    raise AIConfigError("model_registry_invalid")
                models[mid] = _with_tier(models[mid], tier)
        providers, tasks = _parse_policy(raw, models, routes)
        return cls(models, routes, providers=providers, tasks=tasks)

    def resolve(self, provider: str, tier: int) -> ModelSpec:
        mid = self._routes.get(provider, {}).get(tier)
        spec = self._models.get(mid) if mid else None
        if spec is None or not spec.enabled or spec.id.startswith(PLACEHOLDER_PREFIX):
            raise GatewayError("model_not_configured")
        return spec

    def provider_policy(self, provider: str) -> ProviderPolicy:
        """Unlisted providers are `unverified`: nothing is assumed about their data handling."""
        return self._providers.get(provider, ProviderPolicy(provider))

    def has_task(self, task: str) -> bool:
        return task in self._tasks

    def candidates(self, task: str, default_provider: str, default_tier: int) -> list[Candidate]:
        """The ordered models to try for a task. A task without a chain is the single (provider, tier) route.
        Entries whose model is disabled, a placeholder or unknown are skipped here, never guessed."""
        entries = self._tasks.get(task) or [ChainEntry(provider=default_provider, tier=default_tier)]
        out: list[Candidate] = []
        for entry in entries:
            if entry.model is not None:
                spec = self._models.get(entry.model)
                if spec is not None and spec.enabled and not spec.id.startswith(PLACEHOLDER_PREFIX):
                    out.append(Candidate(spec.provider, spec))
            elif entry.tier is not None:
                provider = entry.provider or default_provider  # no provider named: the active one
                spec = self._try(provider, entry.tier)
                if spec is not None:
                    out.append(Candidate(provider, spec))
        return out

    def get(self, model_id: str) -> ModelSpec | None:
        return self._models.get(model_id)

    def configured(self, provider: str) -> list[ModelSpec]:
        return [
            s for t in sorted(self._routes.get(provider, {})) if (s := self._try(provider, t)) is not None
        ]

    def _try(self, provider: str, tier: int) -> ModelSpec | None:
        try:
            return self.resolve(provider, tier)
        except GatewayError:
            return None


def _with_tier(spec: ModelSpec, tier: int) -> ModelSpec:
    return ModelSpec(
        id=spec.id,
        provider=spec.provider,
        tier=tier,
        enabled=spec.enabled,
        priced=spec.priced,
        input_per_mtok_usd=spec.input_per_mtok_usd,
        output_per_mtok_usd=spec.output_per_mtok_usd,
        max_output_tokens=spec.max_output_tokens,
    )


def _parse_policy(
    raw: dict[str, Any], models: dict[str, ModelSpec], routes: dict[str, dict[int, str]]
) -> tuple[dict[str, ProviderPolicy], dict[str, list[ChainEntry]]]:
    try:
        providers: dict[str, ProviderPolicy] = {}
        for name, entry in (raw.get("providers") or {}).items():
            handling = entry.get("data_handling", {})
            state = str(handling.get("zero_retention", "unverified"))
            if state not in RETENTION_STATES:
                raise AIConfigError("model_registry_invalid")
            providers[str(name)] = ProviderPolicy(
                name=str(name),
                zero_retention=state,
                source=str(handling.get("source", "")),
                checked_on=str(handling.get("checked_on", "")),
                notes=str(handling.get("notes", "")),
            )
        tasks: dict[str, list[ChainEntry]] = {}
        for task, chain in (raw.get("tasks") or {}).items():
            entries = []
            for item in chain:
                if "model" in item:
                    if str(item["model"]) not in models:
                        raise AIConfigError("model_registry_invalid")
                    entries.append(ChainEntry(model=str(item["model"])))
                else:
                    tier = int(item["tier"])
                    provider = str(item["provider"]) if "provider" in item else None
                    if provider is not None and tier not in routes.get(provider, {}):
                        raise AIConfigError("model_registry_invalid")
                    entries.append(ChainEntry(provider=provider, tier=tier))
            if not entries:
                raise AIConfigError("model_registry_invalid")
            tasks[str(task)] = entries
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise AIConfigError("model_registry_invalid") from exc
    return providers, tasks
