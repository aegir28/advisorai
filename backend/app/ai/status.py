"""`uv run python -m app.ai.status`: what still stands between this repository and real AI calls.

Read-only. It reads settings and files and prints a checklist; it makes no network call and never
prints a key.
"""

from dataclasses import dataclass

from app.agents.prompts import PromptStore
from app.agents.registry import SpecialtyRegistry
from app.ai.registry import ModelRegistry
from app.ai.types import AIConfigError
from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str


def activation_checklist(settings: Settings) -> list[Check]:
    checks: list[Check] = []
    real = settings.ai_provider == "openai"
    hint = "" if real else " (set openai for real calls)"
    checks.append(Check("provider", real, f"ai_provider={settings.ai_provider}{hint}"))
    has_key = settings.openai_api_key is not None
    checks.append(Check("api key", has_key, "ADVISORAI_OPENAI_API_KEY is " + ("set" if has_key else "empty")))
    try:
        registry = ModelRegistry.from_file(settings.ai_models_file)
        configured = registry.configured("openai")
        for tier in (1, 2, 3):
            ready = any(m.tier == tier for m in configured)
            detail = "configured" if ready else "placeholder: set a real model id"
            checks.append(Check(f"openai tier {tier} model", ready, detail))
        unpriced = [m.id for m in configured if not m.priced]
        if not configured:
            checks.append(Check("openai prices", False, "no model configured yet"))
        else:
            detail = "entered" if not unpriced else "not entered for " + ", ".join(unpriced)
            checks.append(Check("openai prices", not unpriced, detail))
    except AIConfigError as exc:
        checks.append(Check("model registry", False, exc.code))
    for specialty, blockers in SpecialtyRegistry.from_file().readiness(PromptStore()).items():
        checks.append(Check(f"agent {specialty}", not blockers, ", ".join(blockers) or "ready"))
    checks.append(Check("worker", settings.worker_enabled, f"worker_enabled={settings.worker_enabled}"))
    return checks


def main() -> None:
    checks = activation_checklist(get_settings())
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"[{'x' if c.ok else ' '}] {c.name.ljust(width)}  {c.detail}")
    print(f"\n{sum(not c.ok for c in checks)} item(s) still open.")


if __name__ == "__main__":
    main()
