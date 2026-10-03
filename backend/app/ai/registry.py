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


class ModelRegistry:
    def __init__(self, models: dict[str, ModelSpec], routes: dict[str, dict[int, str]]) -> None:
        self._models = models
        self._routes = routes

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
        return cls(models, routes)

    def resolve(self, provider: str, tier: int) -> ModelSpec:
        mid = self._routes.get(provider, {}).get(tier)
        spec = self._models.get(mid) if mid else None
        if spec is None or not spec.enabled or spec.id.startswith(PLACEHOLDER_PREFIX):
            raise GatewayError("model_not_configured")
        return spec

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
