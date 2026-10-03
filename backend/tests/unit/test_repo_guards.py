"""The repository guards (scripts/repo_guards.py): naming, secrets, and the temporary AI-scope boundary."""

import base64
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "repo_guards.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("repo_guards", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guards = load()
OLD_NAME = "Med" + "Clarity"


def rules(files: dict[str, str]) -> set[str]:
    return {f.rule for f in guards.scan(files)}


def test_the_real_repository_is_clean() -> None:
    assert guards.scan(guards.tracked_files()) == []


@pytest.mark.parametrize("text", [OLD_NAME, OLD_NAME.lower(), "med-" + "clarity", "MED_" + "CLARITY"])
def test_the_retired_project_name_is_refused_everywhere(text: str) -> None:
    for path in (
        "README.md",
        "backend/app/x.py",
        "frontend/src/a.tsx",
        "supabase/migrations/1.sql",
        "x.env.example",
    ):
        assert "naming" in rules({path: f"hello {text} world"})


def test_secrets_are_refused() -> None:
    def jwt(role: str) -> str:
        def b(o: object) -> str:
            return base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()

        return f"{b({'alg': 'HS256'})}.{b({'role': role})}.signaturesignature"

    bad = [
        "-----BEGIN " + "PRIVATE KEY-----",
        "sb_secret_" + "abcdefghijkl",
        "sk-" + "a" * 30,
        "AIza" + "a" * 35,
        "GOCSPX-" + "a" * 24,
        "ghp_" + "a" * 36,
        "AKIA" + "A" * 16,
        "sbp_" + "a" * 40,
        "key = " + jwt("service_role"),
    ]
    for text in bad:
        assert "secrets" in rules({"backend/app/x.py": text}), text
    # An anon key is public by design.
    assert rules({"frontend/.env.example": "KEY=" + jwt("anon")}) == set()


def test_environment_files_cannot_be_committed_but_the_example_can() -> None:
    assert "secrets" in rules({"backend/.env": "A=1"})
    assert "secrets" in rules({"frontend/.env.local": "A=1"})
    assert rules({"backend/.env.example": "A=1"}) == set()


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("backend/pyproject.toml", '  "openai>=1.0",'),
        ("backend/pyproject.toml", '  "anthropic",'),
        ("frontend/package.json", '    "@anthropic-ai/sdk": "^0.1",'),
        ("frontend/package.json", '    "@ai-sdk/openai": "^1",'),
        ("backend/pyproject.toml", '  "pgvector",'),
        ("backend/app/ai/gateway.py", "import openai"),
        ("backend/app/ai/gateway.py", "from anthropic import Anthropic"),
        ("frontend/src/ai.ts", 'import OpenAI from "openai"'),
        ("backend/.env.example", "OPENAI_API_KEY="),
        ("backend/app/core/config.py", "gemini_key = os.environ['GEMINI_API_KEY']"),
        ("supabase/migrations/9.sql", "create extension if not exists vector with schema extensions;"),
        ("supabase/migrations/9.sql", "embedding vector(1536)"),
    ],
)
def test_ai_boundary_is_enforced(path: str, text: str) -> None:
    assert "ai-boundary" in rules({path: text}), (path, text)


def test_docs_may_describe_the_future_ai_phase_and_the_supabase_cli_default_is_allowed() -> None:
    assert (
        rules({"docs/handoff-ai-phase.md": "The gateway will read OPENAI_API_KEY and use pgvector."}) == set()
    )
    assert rules({"supabase/config.toml": 'openai_api_key = "env(OPENAI_API_KEY)"'}) == set()
    # Ordinary words are not flagged.
    assert rules({"backend/pyproject.toml": '  "pydantic>=2",  "httpx"'}) == set()


def test_the_gateway_may_exist_but_a_provider_endpoint_outside_the_adapter_may_not() -> None:
    # The gateway and adapter are allowed (they are how AI is supposed to be reached) ...
    assert rules({"backend/app/ai/gateway.py": "from app.ai.provider import Provider"}) == set()
    assert rules({"backend/app/ai/providers/openai.py": 'DEFAULT = "https://api.openai.com/v1"'}) == set()
    # ... but nothing else may name a provider endpoint, and the frontend never may.
    assert "ai-boundary" in rules({"backend/app/services/x.py": 'URL = "https://api.openai.com/v1/x"'})
    assert "ai-boundary" in rules({"frontend/src/lib/x.ts": 'fetch("https://api.anthropic.com/v1/messages")'})
    # The key's real name is fine in settings; the bare provider default name is not.
    assert rules({"backend/app/core/config.py": "openai_api_key: SecretStr | None = None"}) == set()
    assert "ai-boundary" in rules({"backend/app/x.py": 'os.environ["OPENAI_API_KEY"]'})


CLOUD = guards.CLOUD_DEPLOY_WORKFLOW


def cloud_rules(text: str) -> set[str]:
    return {f.rule for f in guards.scan({CLOUD: text})}


def good_cloud() -> str:
    return (Path(__file__).resolve().parents[3] / CLOUD).read_text(encoding="utf-8")


def test_the_cloud_deploy_workflow_is_as_designed() -> None:
    assert guards.check_cloud_deploy(good_cloud()) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("on:\n  workflow_dispatch:", "on:\n  push:\n    branches: [develop]\n  workflow_dispatch:"),
        ("on:\n  workflow_dispatch:", "on:\n  pull_request:\n  workflow_dispatch:"),
        ("on:\n  workflow_dispatch:", "on:\n  schedule:\n    - cron: '0 3 * * *'\n  workflow_dispatch:"),
        ("supabase db push --yes", "supabase db reset --linked"),
        ("supabase db push --yes", "supabase db push --include-all"),
        ("supabase db push --yes", "supabase db push --force"),
        ("supabase migration list", "supabase migration repair --status reverted 1"),
        ("supabase migration list", "psql \"$URL\" -c 'select 1'"),
        ("cancel-in-progress: false", "cancel-in-progress: true"),
        ("SUPABASE_PROJECT_REF: mutwtdtqohmhsrgrkvwd", "SUPABASE_PROJECT_REF: abcdefghijklmnopqrst"),
        ('--project-ref "$SUPABASE_PROJECT_REF"', "--project-ref abcdefghijklmnopqrst"),
        ("SUPABASE_DB_PASSWORD: ${{ secrets.SUPABASE_DB_PASSWORD }}", "SUPABASE_DB_PASSWORD: hunter2"),
        ("SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}", "SUPABASE_ACCESS_TOKEN: abc"),
    ],
)
def test_a_cloud_deploy_workflow_that_breaks_a_safety_rule_is_refused(old: str, new: str) -> None:
    text = good_cloud()
    assert old in text
    assert "cloud-deploy" in cloud_rules(text.replace(old, new, 1))


def test_the_local_ci_workflow_may_still_reset_its_throwaway_database() -> None:
    assert "supabase db reset" in (Path(SCRIPT).parents[1] / ".github/workflows/supabase.yml").read_text()
    assert guards.scan({".github/workflows/supabase.yml": "run: supabase db reset"}) == []
