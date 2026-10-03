"""Case signals: deterministic, content-free facts about a structured case that registry triggers refer to.

`registry/signals.yaml` holds the word lists (configuration, not code). Matching is whole-word and case-blind,
over the structured case only (it is already de-identified by contract). The result is COUNTS per signal: a
trigger's reason is fixed text, and the router appends only how many terms matched, never which words, so the
routing trace stays free of case content.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.schemas.case import CaseV1

DEFAULT_FILE = Path(__file__).resolve().parents[3] / "registry" / "signals.yaml"
BUILTIN_SIGNALS = frozenset({"always", "medications_present"})


class SignalConfigError(Exception):
    """signals_config_invalid. The message is a fixed code."""


@dataclass(frozen=True, slots=True)
class SignalHit:
    signal: str
    matches: int
    # Which parts of the case matched (field names only, never text).
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaseSignals:
    hits: dict[str, SignalHit]

    def has(self, signal: str) -> bool:
        return signal in self.hits

    def count(self, signal: str) -> int:
        hit = self.hits.get(signal)
        return hit.matches if hit else 0

    def names(self) -> list[str]:
        return sorted(self.hits)


class SignalExtractor:
    def __init__(self, lexicons: dict[str, list[str]], fields: list[str]) -> None:
        self._fields = fields
        self._patterns = {
            name: re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(t) for t in terms) + r")(?![\w-])", re.I)
            for name, terms in lexicons.items()
            if terms
        }

    @classmethod
    def from_file(cls, path: Path = DEFAULT_FILE) -> "SignalExtractor":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if raw["version"] != 1:
                raise SignalConfigError("signals_config_invalid")
            lexicons = {str(k): [str(t).lower() for t in v["terms"]] for k, v in raw["signals"].items()}
            fields = [str(f) for f in raw["fields"]]
        except SignalConfigError:
            raise
        except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError) as exc:
            raise SignalConfigError("signals_config_invalid") from exc
        clash = BUILTIN_SIGNALS & set(lexicons)
        if clash or any(not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", n) for n in lexicons):
            raise SignalConfigError("signals_config_invalid")
        return cls(lexicons, fields)

    @property
    def lexicon_signals(self) -> frozenset[str]:
        return frozenset(self._patterns)

    def extract(self, case: CaseV1) -> CaseSignals:
        parts = _case_text_by_field(case)
        hits: dict[str, SignalHit] = {"always": SignalHit("always", 1, ())}
        if case.medications:
            hits["medications_present"] = SignalHit(
                "medications_present", len(case.medications), ("medications",)
            )
        for name, pattern in self._patterns.items():
            total = 0
            matched_fields: list[str] = []
            for field in self._fields:
                n = len(pattern.findall(parts.get(field, "")))
                if n:
                    total += n
                    matched_fields.append(field)
            if total:
                hits[name] = SignalHit(name, total, tuple(matched_fields))
        return CaseSignals(hits)


def _case_text_by_field(case: CaseV1) -> dict[str, str]:
    inv = case.investigations
    return {
        "chief_concern": case.chief_concern,
        "symptoms": " ; ".join(s.text for s in case.symptoms),
        "diagnoses": " ; ".join(d.name for d in case.diagnoses),
        "history": " ; ".join(h.text for h in case.history),
        "procedures": " ; ".join(p.text for p in case.procedures),
        "surgeries": " ; ".join(s.text for s in case.surgeries),
        "treatment_history": " ; ".join(t.text for t in case.treatment_history),
        "recommendations": " ; ".join(r.text for r in case.recommendations),
        "proposed": " ; ".join([*case.proposed.treatment, *case.proposed.procedure]),
        "investigations": " ; ".join(
            i.name for group in (inv.labs, inv.imaging, inv.ecg, inv.pathology) for i in group
        ),
    }
