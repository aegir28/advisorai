"""The PII boundary: rule-based de-identification and the residual check. Synthetic strings only."""

import pytest

from app.safety.deidentify import deidentify, find_residual

SYNTHETIC = (
    "Patient name: Meera Nair, DOB: 12/03/1970. Email meera.n@example.org, phone +91 98765 43210, "
    "MRN: AB12345. Dr. Anil Verma reviewed on 10 Feb 2026: troponin 182 ng/L, HbA1c 8.9 %, BP 140/90, "
    "aspirin 75 mg. Aadhaar 1234 5678 9012. See https://hospital.example/records/9."
)


def test_identifiers_are_replaced_and_clinical_content_is_kept() -> None:
    result = deidentify(SYNTHETIC, known_identifiers=["Meera Nair"])
    for gone in (
        "Meera",
        "meera.n@example.org",
        "98765",
        "AB12345",
        "Anil Verma",
        "1234 5678",
        "hospital.example",
        "12/03/1970",
    ):
        assert gone not in result.text, gone
    for kept in ("10 Feb 2026", "troponin 182 ng/L", "HbA1c 8.9 %", "BP 140/90", "aspirin 75 mg"):
        assert kept in result.text, kept
    assert {"email", "phone", "record_id", "date_of_birth", "government_id", "url", "name"} <= set(
        result.counts
    )
    assert find_residual(result.text) == []


def test_counts_describe_what_was_removed_but_never_contain_it() -> None:
    result = deidentify(SYNTHETIC, known_identifiers=["Meera Nair"])
    assert all(isinstance(v, int) for v in result.counts.values())
    assert "Meera" not in repr(result.counts)


def test_known_identifiers_are_matched_case_insensitively_everywhere() -> None:
    result = deidentify("MEERA NAIR said meera nair is anxious", known_identifiers=["Meera Nair"])
    assert "meera" not in result.text.casefold()
    assert result.counts["known_identifier"] == 2


def test_text_without_identifiers_is_unchanged() -> None:
    text = "Chest tightness on climbing stairs since January; LDL 142 mg/dL; metformin 500 mg twice daily."
    result = deidentify(text)
    assert result.text == text and not result.changed


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("write to a.b@c.org", "email"),
        ("call 9876543210", "phone"),
        ("id 1234-5678-9012", "government_id"),
        ("see https://x.example/p", "url"),
    ],
)
def test_residual_check_flags_what_the_rules_must_never_let_through(text: str, category: str) -> None:
    assert category in find_residual(text)


def test_the_rules_are_deterministic() -> None:
    assert deidentify(SYNTHETIC, known_identifiers=["Meera Nair"]) == deidentify(
        SYNTHETIC, known_identifiers=["Meera Nair"]
    )
