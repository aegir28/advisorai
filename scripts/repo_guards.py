#!/usr/bin/env python3
"""Repository guards, run in CI (`.github/workflows/guards.yml`) and by
`backend/tests/unit/test_repo_guards.py`.

Standard library only. Exit code 1 and a list of findings when a rule is broken.

  naming     The project is AdvisorAI. The old blueprint's working title must not appear in tracked files.
  secrets    No private keys, service-role/secret keys, provider API keys or committed .env files.
  ai-boundary  The AI gateway (backend/app/ai) is the only door to a model provider, and it speaks plain
             HTTP. So: no provider SDK dependency or import anywhere, no bare provider key names (the key is
             ADVISORAI_OPENAI_API_KEY, read in settings only), no provider endpoint outside the adapter,
             config and tests, and no pgvector/vector column (embeddings are not chosen yet). This replaced
             the Phase 2 rule that forbade any AI code; the boundary is now "AI only through the gateway".
  cloud-deploy  The manual Supabase Cloud deployment workflow stays manual-only, forward-only, pinned to the
             AdvisorAI project, serialized, and reads its credentials only from GitHub secrets.
"""

import base64
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The retired working title, spelled so this file does not trip its own rule.
_FORBIDDEN_NAME = re.compile("med" + r"[ _-]?" + "clarity", re.IGNORECASE)

_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".mts",
    ".js",
    ".mjs",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".md",
    ".sql",
    ".txt",
    ".css",
    ".html",
    ".example",
    ".cfg",
    ".ini",
    ".lock",
    ".conf",
}
_SKIP_PARTS = {"node_modules", ".next", ".git", "uv.lock", "package-lock.json"}

_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "Supabase secret key": re.compile(r"\bsb_secret_[A-Za-z0-9_-]{8,}"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Google OAuth client secret": re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{30,}"),
    "Supabase access token": re.compile(r"\bsbp_[A-Za-z0-9]{20,}"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.(eyJ[A-Za-z0-9_-]{8,})\.[A-Za-z0-9_-]{8,}")

# ai-boundary: package names (dependency files), identifiers (code/config) and provider endpoints.
_AI_PACKAGES = re.compile(
    r"(?i)(?<![\w-])(openai|anthropic|@anthropic-ai/sdk|google-generativeai|google-genai|@google/generative-ai|"
    r"@google/genai|@ai-sdk/[\w-]+|litellm|langchain[\w-]*|llama[-_]index|cohere|mistralai|sentence-transformers|"
    r"pgvector|tiktoken|vertexai|google-cloud-aiplatform)(?![\w-])"
)
_AI_ENV_NAMES = re.compile(
    r"\b(OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|AZURE_OPENAI\w*|COHERE_API_KEY|"
    r"MISTRAL_API_KEY|OPENROUTER_API_KEY|GROQ_API_KEY)\b"
)
_AI_ENDPOINTS = re.compile(
    r"(?i)api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|api\.cohere\.(?:ai|com)"
)
# The only files that may name a provider endpoint: the adapter, the settings default, the tests of both.
_ENDPOINT_ALLOWLIST = {
    "backend/app/ai/providers/openai.py",
    "backend/app/core/config.py",
    "backend/tests/unit/test_ai_openai_adapter.py",
    "backend/tests/unit/test_ai_config.py",
}
_AI_SQL = re.compile(r"(?i)\bcreate\s+extension\b[^;]*\bvector\b|\bvector\s*\(\s*\d+\s*\)")
_DEPENDENCY_FILES = {"pyproject.toml", "package.json", "requirements.txt", "requirements-dev.txt"}
# Files that may name provider env vars: the Supabase CLI's own Studio setting, and the guard + its tests.
_AI_ALLOWLIST = {
    "supabase/config.toml",
    "scripts/repo_guards.py",
    "backend/tests/unit/test_repo_guards.py",
}
# Docs may describe the future AI phase.
_DOC_SUFFIXES = {".md"}


CLOUD_DEPLOY_WORKFLOW = ".github/workflows/supabase-cloud-deploy.yml"
CLOUD_PROJECT_REF = "mutwtdtqohmhsrgrkvwd"
# Anything that could change or discard data, or replay history, is refused in the cloud workflow.
_CLOUD_FORBIDDEN = re.compile(
    r"(?i)\bdb\s+reset\b|\bdb\s+(?:push|pull|remote)\b[^\n]*--(?:include-all|include-roles|include-seed|force)\b"
    r"|\bmigration\s+(?:repair|squash)\b|\bdb\s+(?:execute|query)\b|\bpsql\b|\bdrop\s+(?:table|schema|database)\b"
    r"|\btruncate\b|\bsupabase\s+(?:projects\s+delete|branches\s+delete)\b"
)
_CLOUD_SECRET_NAMES = ("SUPABASE_ACCESS_TOKEN", "SUPABASE_DB_PASSWORD")


def check_cloud_deploy(text: str) -> list[str]:
    """Problems with the cloud deployment workflow's text (empty when it is as designed)."""
    problems: list[str] = []
    triggers = re.search(r"(?m)^on:\s*\n((?:[ \t]+.*\n|\n)+)", text)
    keys = re.findall(r"(?m)^  ([a-z_]+):", triggers.group(1)) if triggers else []
    if keys != ["workflow_dispatch"]:
        problems.append(f"must be workflow_dispatch only (found triggers: {keys or 'none'})")
    if not re.search(
        r"(?m)^concurrency:\s*\n\s+group: supabase-cloud-deploy\s*\n\s+cancel-in-progress: false", text
    ):
        problems.append("needs the serial concurrency guard (cancel-in-progress: false)")
    if f"SUPABASE_PROJECT_REF: {CLOUD_PROJECT_REF}" not in text:
        problems.append("SUPABASE_PROJECT_REF must be the AdvisorAI project")
    if re.search(r"--project-ref\s+(?!\"\$SUPABASE_PROJECT_REF\")", text):
        problems.append("link only to $SUPABASE_PROJECT_REF")
    if "supabase db push" not in text:
        problems.append("must deploy with `supabase db push`")
    for line in text.splitlines():
        if _CLOUD_FORBIDDEN.search(line):
            problems.append(f"forbidden command: {line.strip()[:80]}")
    for name in _CLOUD_SECRET_NAMES:
        if f"${{{{ secrets.{name} }}}}" not in text:
            problems.append(f"{name} must come from `${{{{ secrets.{name} }}}}`")
        for line in text.splitlines():
            if re.match(rf"\s*{name}:\s*(?!\$\{{\{{ secrets\.{name} \}}\}}\s*$)\S", line):
                problems.append(f"{name} must not be set to a literal")
    return problems


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.path}:{self.line}: {self.message}"


def _jwt_role(payload_b64: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        role = json.loads(raw).get("role")
        return role if isinstance(role, str) else None
    except (ValueError, AttributeError):
        return None


def scan(files: dict[str, str]) -> list[Finding]:
    """`files` maps a repository-relative path to its text."""
    findings: list[Finding] = []
    for path, text in sorted(files.items()):
        name = path.rsplit("/", 1)[-1]
        suffix = Path(path).suffix
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            findings.append(Finding("secrets", path, 1, "an environment file must not be committed"))
        for number, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN_NAME.search(line):
                findings.append(Finding("naming", path, number, "the project is named AdvisorAI"))
            for label, pattern in _SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append(Finding("secrets", path, number, f"looks like a {label}"))
            for match in _JWT.finditer(line):
                if _jwt_role(match.group(1)) == "service_role":
                    findings.append(Finding("secrets", path, number, "a service_role JWT"))
            if path in _AI_ALLOWLIST or suffix in _DOC_SUFFIXES:
                continue
            endpoint_ok = path in _ENDPOINT_ALLOWLIST or suffix == ".yaml" or name == ".env.example"
            if _AI_ENDPOINTS.search(line) and not endpoint_ok:
                findings.append(
                    Finding("ai-boundary", path, number, "provider endpoint outside the gateway adapter")
                )
            if name in _DEPENDENCY_FILES and _AI_PACKAGES.search(line):
                findings.append(
                    Finding("ai-boundary", path, number, "AI provider SDK / embedding dependency (use HTTP)")
                )
            elif suffix in {".py", ".ts", ".tsx", ".mts", ".mjs", ".js"} and re.search(
                r"""(?:import|from|require\()\s*['"]?\s*(?:openai|anthropic|google\.generativeai|google\.genai|"""
                r"""@anthropic-ai|@google/generative-ai|@ai-sdk|litellm|langchain|pgvector)\b""",
                line,
            ):
                findings.append(
                    Finding("ai-boundary", path, number, "AI provider SDK import (use the gateway)")
                )
            if _AI_ENV_NAMES.search(line):
                findings.append(
                    Finding("ai-boundary", path, number, "bare AI provider key name (use the ADVISORAI_ one)")
                )
            if suffix == ".sql" and _AI_SQL.search(line):
                findings.append(
                    Finding(
                        "ai-boundary",
                        path,
                        number,
                        "pgvector / vector column (embeddings are not chosen yet)",
                    )
                )
    cloud = files.get(CLOUD_DEPLOY_WORKFLOW)
    if cloud is not None:
        findings.extend(
            Finding("cloud-deploy", CLOUD_DEPLOY_WORKFLOW, 1, p) for p in check_cloud_deploy(cloud)
        )
    return findings


def tracked_files(root: Path = ROOT) -> dict[str, str]:
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    files: dict[str, str] = {}
    for rel in filter(None, listing):
        parts = set(Path(rel).parts) | {Path(rel).name}
        if parts & _SKIP_PARTS:
            continue
        path = root / rel
        if path.suffix not in _TEXT_SUFFIXES and path.name not in {
            ".gitignore",
            ".gitattributes",
            ".env.example",
        }:
            continue
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return files


def main(argv: Iterable[str] = ()) -> int:
    del argv
    findings = scan(tracked_files())
    for finding in findings:
        print(finding)
    if findings:
        print(f"\n{len(findings)} finding(s).", file=sys.stderr)
        return 1
    print("repo guards: ok (naming, secrets, ai-boundary, cloud-deploy)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
