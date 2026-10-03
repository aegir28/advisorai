"""Output safety: the lint that blocks unsafe model text, readability, and the medication-review contract."""

import copy
import glob
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.validate import errors, validate_medication_review
from app.safety.output_lint import lint_document, lint_evidence_ids, lint_text
from app.safety.readability import grade_level, reading_ok, syllables
from app.schemas import CaseV1
from app.schemas.medication_review import MedicationReview

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def rules(text: str, kind: str = "interpretation") -> set[str]:
    return {v.rule for v in lint_text(text, kind)}  # type: ignore[arg-type]


# ── what must be blocked ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    [
        "Stop taking aspirin.",
        "You should stop taking metformin now.",
        "Please discontinue the medicine.",
        "Start taking a statin.",
        "Increase your dose of metoprolol.",
        "Cut down your dose of insulin.",
        "Do not take ibuprofen.",
        "I recommend you reduce the dosage.",
        "You must come off the tablets.",
    ],
)
def test_an_instruction_to_stop_start_or_change_a_medicine_is_blocked(text: str) -> None:
    assert "medication_directive" in rules(text)


@pytest.mark.parametrize("text", ["Take 10 mg of aspirin daily.", "I prescribe 5 mg at night."])
def test_dosing_instructions_are_blocked(text: str) -> None:
    assert "prescribing" in rules(text)


@pytest.mark.parametrize(
    "text",
    [
        "Your doctor is wrong about this.",
        "The cardiologist was mistaken.",
        "This was a misdiagnosis.",
        "That is malpractice.",
    ],
)
def test_saying_a_doctor_is_wrong_is_blocked(text: str) -> None:
    assert "doctor_wrong" in rules(text)


@pytest.mark.parametrize(
    "text",
    [
        "Doctor A is better than Doctor B.",
        "The second opinion is the winner.",
        "You should switch doctors.",
        "Go with the second opinion.",
        "Opinion B is more reliable.",
        "Specialist B was more qualified than the first.",
    ],
)
def test_ranking_doctors_or_picking_a_winner_is_blocked(text: str) -> None:
    assert "doctor_ranking" in rules(text)


@pytest.mark.parametrize(
    "text", ["This definitely means a blockage.", "This proves that you need surgery.", "It is 100% certain."]
)
def test_unsupported_certainty_is_blocked(text: str) -> None:
    assert "unsupported_certainty" in rules(text)


def test_a_definitive_diagnosis_is_blocked_unless_it_is_a_documented_fact() -> None:
    assert "definitive_diagnosis" in rules("You have heart failure.")
    assert "definitive_diagnosis" not in rules("You have type 2 diabetes.", "patient_fact")
    assert "definitive_diagnosis" not in rules("You have had chest tightness since January.")


@pytest.mark.parametrize(
    "text",
    [
        "See Smith et al., 2019 for details.",
        "PMID: 123456 supports this.",
        "Read https://example.org/paper.",
        "As shown in [12].",
    ],
)
def test_free_text_citations_are_blocked(text: str) -> None:
    assert "unsourced_citation" in rules(text)


def test_unknown_evidence_ids_are_reported() -> None:
    assert lint_evidence_ids(["e1", "x9"], {"e1", "e2"})[0].rule == "unknown_evidence_id"
    assert lint_evidence_ids(["e1"], {"e1"}) == []


# ── what must be allowed: discussion framing and documented facts ────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    [
        "Ask your doctor whether it could be reasonable to stop taking aspirin.",
        "Is it worth discussing whether the dose of metformin should change?",
        "The record says metformin was stopped in March.",
        "Two documents describe the scan differently; both are kept.",
        "Aspirin 75 mg, once daily.",
        "The discharge summary lists a different dose from the GP list. Bring both to your visit.",
        "Please do not change any medicine on your own.",
        "Do not stop any medicine without talking to your doctor first.",
        "Perspectives differ on timing, and both views are kept.",
    ],
)
def test_discussion_framing_and_documented_facts_are_allowed(text: str) -> None:
    assert lint_text(text, "patient_fact") == [] and lint_text(text) == []


def test_a_violation_never_contains_the_text() -> None:
    secret = "Stop taking Zyloprimex immediately."
    found = lint_text(secret)
    assert found and "Zyloprimex" not in " ".join(str(v) for v in found)


def test_the_shipped_synthetic_fixtures_pass_the_lint() -> None:
    """Calibration: the project's own fictional reports, questions, comparisons and syntheses are clean."""
    checked = 0
    for name in glob.glob(str(FIX / "*" / "*.json")):
        data = json.loads(Path(name).read_text())
        for item in data if isinstance(data, list) else [data]:
            assert lint_document(item) == [], name
            checked += 1
    assert checked > 20


def test_lint_document_inherits_the_kind_of_the_enclosing_item() -> None:
    doc = {
        "items": [
            {"kind": "patient_fact", "text": "You have type 2 diabetes mellitus."},
            {"kind": "interpretation", "text": "You have heart failure."},
        ]
    }
    assert [(k, v.rule) for k, v in lint_document(doc)] == [("text", "definitive_diagnosis")]


# ── readability ────────────────────────────────────────────────────────────────────────────────────
def test_readability_is_a_stable_measurement() -> None:
    assert syllables("angiography") >= 4 and syllables("cat") == 1
    simple = "Your heart test showed a narrow pipe. Ask your doctor what it means. It is a good question."
    hard = "Percutaneous coronary intervention constitutes a revascularisation modality contingent upon angiographic stenosis."
    assert grade_level(simple) < 6 < grade_level(hard)
    assert reading_ok(simple) and not reading_ok(hard) and grade_level("") == 0.0


# ── medication review contract and validator ─────────────────────────────────────────────────────────
def case() -> CaseV1:
    return CaseV1.model_validate(json.loads((FIX / "cardiology" / "case.v1.json").read_text()))


def good_review(c: CaseV1) -> dict[str, Any]:
    medicines = [
        {
            "id": f"m{i}",
            "medication": m.name,
            "fact_refs": [m.fact_ref],
            "purpose": {"status": "not_documented"},
            "dose": {"status": "documented", "value": m.dose} if m.dose else {"status": "not_documented"},
            "frequency": {"status": "documented", "value": m.freq}
            if m.freq
            else {"status": "not_documented"},
            "duration": {"status": "not_documented"},
        }
        for i, m in enumerate(c.medications)
    ]
    return {
        "schema_version": "medication_review.v1",
        "medicines": medicines,
        "concerns": [
            {
                "id": "c1",
                "kind": "purpose_not_documented",
                "statement": "The record does not say what some medicines are for.",
                "basis": "patient_record",
                "medication_ids": ["m0"],
                "fact_refs": [c.medications[0].fact_ref],
                "source_ids": [],
            }
        ],
        "discussion_points": [
            {
                "id": "d1",
                "text": "Ask what each medicine is for and how long it is meant to continue.",
                "linked_to": ["c1"],
            }
        ],
        "missing_information": ["Purpose and duration of each medicine"],
        "limitations": ["Based only on the documents provided."],
    }


def test_a_good_medication_review_validates() -> None:
    c = case()
    review = MedicationReview.model_validate(good_review(c))
    assert errors(validate_medication_review(review, c, set())) == []


def test_every_documented_medicine_must_be_reviewed() -> None:
    c = case()
    raw = good_review(c)
    raw["medicines"] = raw["medicines"][1:]
    raw["concerns"][0]["medication_ids"] = [raw["medicines"][0]["id"]]
    raw["discussion_points"][0]["linked_to"] = ["c1"]
    codes = {v.code for v in validate_medication_review(MedicationReview.model_validate(raw), c, set())}
    assert "medication_not_reviewed" in codes


def test_a_concern_needs_evidence_of_its_stated_basis() -> None:
    c = case()
    raw = good_review(c)
    raw["concerns"][0]["fact_refs"] = []
    with pytest.raises(ValidationError):
        MedicationReview.model_validate(raw)
    raw = good_review(c)
    raw["concerns"][0].update(basis="external_reference", fact_refs=[], source_ids=[])
    with pytest.raises(ValidationError):
        MedicationReview.model_validate(raw)


def test_unknown_references_and_sources_are_reported() -> None:
    c = case()
    raw = good_review(c)
    raw["concerns"][0].update(fact_refs=["nope"], medication_ids=["m0", "mX"], source_ids=["src_x"])
    raw["discussion_points"][0]["linked_to"] = ["zzz"]
    codes = {v.code for v in validate_medication_review(MedicationReview.model_validate(raw), c, {"src_ok"})}
    assert {
        "unknown_fact_ref",
        "concern_unknown_medicine",
        "unknown_source",
        "discussion_unknown_ref",
    } <= codes


def test_an_instruction_inside_a_medication_review_is_rejected_by_the_validator() -> None:
    c = case()
    raw = good_review(c)
    raw["discussion_points"][0]["text"] = "You should stop taking diclofenac now."
    codes = {v.code for v in validate_medication_review(MedicationReview.model_validate(raw), c, set())}
    assert "unsafe_text:medication_directive" in codes
    raw = good_review(c)
    raw["concerns"][0]["statement"] = "The current doctor is wrong to have prescribed this."
    codes = {v.code for v in validate_medication_review(MedicationReview.model_validate(raw), c, set())}
    assert "unsafe_text:doctor_wrong" in codes


def test_documented_values_are_consistent() -> None:
    for bad in (
        {"status": "documented"},
        {"status": "documented", "value": "  "},
        {"status": "not_documented", "value": "5 mg"},
    ):
        raw = copy.deepcopy(good_review(case()))
        raw["medicines"][0]["dose"] = bad
        with pytest.raises(ValidationError):
            MedicationReview.model_validate(raw)
