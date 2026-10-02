"""The safety gate: a deterministic, rule-based red-flag screen. No AI, no network, nothing stored.

It is a port of the frontend prototype's rules (`frontend/src/mocks/mock-api.ts`), kept identical by a
shared fixture that both test suites run (`backend/tests/fixtures/safety_cases.json`). It only decides
whether to stop and say "get urgent care now"; it never interprets, diagnoses or advises beyond that.

The text it reads is free text a person typed. It is NEVER logged, audited or returned in full: only the
short matched phrases come back, so the screen can show why it stopped.
"""

import re
from dataclasses import dataclass
from typing import Final, Literal

Category = Literal["cardiac", "stroke", "breathing", "bleeding", "self_harm"]

_RULES: Final[tuple[tuple[re.Pattern[str], Category], ...]] = (
    (re.compile(r"chest pain (right )?now|pain in (my )?chest (right )?now|crushing chest", re.I), "cardiac"),
    (re.compile(r"stroke|face (is )?drooping|slurred speech|sudden weakness", re.I), "stroke"),
    (
        re.compile(
            r"can'?t breathe|cannot breathe|breathless at rest|short of breath at rest|struggling to breathe",
            re.I,
        ),
        "breathing",
    ),
    (re.compile(r"heavy bleeding|bleeding (heavily|a lot)|won'?t stop bleeding", re.I), "bleeding"),
    (re.compile(r"suicid|kill myself|end my life|want to die|harm myself", re.I), "self_harm"),
)

# The checkboxes the form shows, mapped to a category.
_SYMPTOM_CATEGORY: Final[dict[str, Category]] = {
    "chest_pain_now": "cardiac",
    "stroke_signs": "stroke",
    "breathless_rest": "breathing",
    "heavy_bleeding": "bleeding",
    "self_harm": "self_harm",
}
_MAX_MATCH_LENGTH = 60


@dataclass(frozen=True, slots=True)
class SafetyResult:
    red_flag: bool
    matched: list[str]
    category: Category | None


def check(text: str, current_symptoms: list[str]) -> SafetyResult:
    matched: list[str] = []
    category: Category | None = None
    for symptom in current_symptoms:
        # Only the known checkbox keys are echoed back, never arbitrary client text.
        if symptom in _SYMPTOM_CATEGORY:
            matched.append(symptom)
            category = category or _SYMPTOM_CATEGORY[symptom]
    for pattern, rule_category in _RULES:
        hit = pattern.search(text)
        if hit:
            matched.append(hit.group(0)[:_MAX_MATCH_LENGTH])
            category = category or rule_category
    return SafetyResult(red_flag=bool(matched), matched=matched, category=category)
