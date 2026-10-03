"""Orchestration prompts: version-controlled files in `prompts/`, loaded by name, hashed for observability.

A prompt's `name_vN.md` file is the single source; its sha256 is what usage and audit records carry as the
prompt version, so any answer can be tied to the exact text that produced it. Placeholders are refused.
"""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "prompts"


class PromptError(Exception):
    """prompt_missing or prompt_empty. The message is a fixed code."""


@dataclass(frozen=True, slots=True)
class OrchPrompt:
    name: str
    version: int
    text: str
    sha256: str

    @property
    def id(self) -> str:
        return f"{self.name}_v{self.version}@{self.sha256[:8]}"


@lru_cache(maxsize=64)
def load(name: str, version: int = 1) -> OrchPrompt:
    try:
        text = (ROOT / f"{name}_v{version}.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError("prompt_missing") from exc
    if not text.strip() or text.lstrip().startswith("<!-- PLACEHOLDER"):
        raise PromptError("prompt_empty")
    return OrchPrompt(name, version, text.strip(), hashlib.sha256(text.encode()).hexdigest())


def specialist_prompt(focus: str, *, medication: bool) -> OrchPrompt:
    """The shared specialist base with the registry's one-sentence focus filled in (+ the medicine addendum)."""
    base = load("specialist_base")
    text = base.text.replace("{{focus}}", focus.strip())
    if medication:
        text = f"{text}\n\n{load('medication_addendum').text}"
    return OrchPrompt("specialist", base.version, text, hashlib.sha256(text.encode()).hexdigest())
