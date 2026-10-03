"""The rule-based safety gate and its endpoint contract. Shares its cases with the frontend test."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.safety.red_flags import check

CASES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "safety_cases.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    result = check(case["text"], case["currentSymptoms"])
    assert result.red_flag is case["redFlag"]
    assert result.matched == case["matched"]
    assert result.category == case["category"]


def test_unknown_symptom_keys_are_never_echoed() -> None:
    result = check("", ["<script>alert(1)</script>", "patient name is X"])
    assert result.matched == [] and result.red_flag is False


def test_a_match_is_short() -> None:
    result = check("suicid" + "e" * 500, [])
    assert result.matched == ["suicid" + "e" * 0] or all(len(m) <= 60 for m in result.matched)
