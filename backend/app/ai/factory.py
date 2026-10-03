"""Build the gateway from settings: where a provider is chosen and where the key is read."""

from app.ai.budget import BudgetGuard, LedgerBudgetGuard, SpendReader, inr_to_micro_usd
from app.ai.gateway import AIGateway, GatewayConfig
from app.ai.provider import Provider
from app.ai.providers.fake import FakeProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.registry import ModelRegistry
from app.ai.types import AIConfigError
from app.ai.usage import UsageSink
from app.audit.writer import AuditRecorder
from app.core.config import Settings

_MICROS = 1_000_000


def build_provider(settings: Settings) -> Provider:
    if settings.ai_provider == "fake":
        return FakeProvider()
    if settings.openai_api_key is None:
        # Reached only if validation was bypassed; Settings refuses this combination.
        raise AIConfigError("openai_api_key_missing")
    return OpenAIProvider(settings.openai_api_key, base_url=settings.openai_base_url)


def build_gateway(
    settings: Settings,
    *,
    provider: Provider | None = None,
    sink: UsageSink | None = None,
    audit: AuditRecorder | None = None,
    spend_reader: SpendReader | None = None,
) -> AIGateway:
    registry = ModelRegistry.from_file(settings.ai_models_file)
    provider = provider or build_provider(settings)
    guard: BudgetGuard | None = None
    if settings.ai_total_budget_inr > 0 and spend_reader is not None:
        guard = LedgerBudgetGuard(
            inr_to_micro_usd(settings.ai_total_budget_inr, settings.ai_inr_per_usd),
            spend_reader,
            reserve_fraction=settings.ai_budget_reserve_fraction,
        )
    elif settings.ai_provider != "fake":
        # Settings already demands the ledger for a live provider; this is the belt to that braces.
        raise AIConfigError("budget_guard_unavailable")
    return AIGateway(
        provider,
        registry,
        guard=guard,
        config=GatewayConfig(
            request_timeout_s=settings.ai_request_timeout_seconds,
            max_attempts=settings.ai_max_attempts,
            schema_retries=settings.ai_schema_retries,
            run_budget_micro_usd=int(settings.ai_run_budget_usd * _MICROS),
            privacy_policy=settings.ai_privacy_policy,
        ),
        sink=sink,
        audit=audit,
    )
