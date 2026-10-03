"""Prompt store: version-controlled prompt files, with placeholders refused."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER_MARKER = "<!-- PLACEHOLDER"
DEFAULT_ROOT = Path(__file__).resolve().parent / "prompts"


class PromptNotWrittenError(Exception):
    """The prompt file is missing or still a placeholder. The message is a fixed code."""


@dataclass(frozen=True, slots=True)
class Prompt:
    specialty: str
    version: int
    text: str
    sha256: str


class PromptStore:
    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self._root = root

    def path(self, specialty: str, version: int) -> Path:
        return self._root / specialty / f"v{version}.md"

    def get(self, specialty: str, version: int) -> Prompt:
        path = self.path(specialty, version)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PromptNotWrittenError("prompt_missing") from exc
        if not text.strip() or text.lstrip().startswith(PLACEHOLDER_MARKER):
            raise PromptNotWrittenError("prompt_not_written")
        return Prompt(specialty, version, text, hashlib.sha256(text.encode()).hexdigest())

    def is_written(self, specialty: str, version: int) -> bool:
        try:
            self.get(specialty, version)
        except PromptNotWrittenError:
            return False
        return True
