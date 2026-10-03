"""Evidence contracts, the deterministic retriever test double, and structural claim checks."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evidence.contracts import EvidenceItem, RetrievalQuery
from app.evidence.retrieval import KeywordRetriever
from app.evidence.verify import check_claim_structure
from app.schemas import Claim, EvidenceData
from app.schemas.common import ExternalSource, SourceRef

pytestmark = pytest.mark.anyio
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def source(i: str, snippet: str) -> ExternalSource:
    return ExternalSource(
        id=i, title="t", publisher="p", year=2026, licence="synthetic", section="s", snippet=snippet
    )


def external(i: str, snippet: str) -> EvidenceItem:
    return EvidenceItem(id=i, origin="external_reference", external_source=source(i, snippet))


def patient(i: str, snippet: str) -> EvidenceItem:
    return EvidenceItem(
        id=i, origin="patient_document", patient_source=SourceRef(doc_id="d", page=1, snippet=snippet)
    )


def test_an_item_has_exactly_one_source_matching_its_origin() -> None:
    assert external("e", "x").snippet == "x" and patient("p", "y").snippet == "y"
    with pytest.raises(ValidationError):
        EvidenceItem(id="a", origin="patient_document")
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="a", origin="external_reference", patient_source=SourceRef(doc_id="d", page=1, snippet="s")
        )
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="a",
            origin="patient_document",
            patient_source=SourceRef(doc_id="d", page=1, snippet="s"),
            external_source=source("s", "x"),
        )


async def test_the_keyword_retriever_ranks_filters_and_limits_deterministically() -> None:
    items = [
        external("e1", "troponin raised marker"),
        external("e2", "troponin"),
        patient("p1", "troponin raised value found"),
        external("e3", "unrelated"),
    ]
    retriever = KeywordRetriever(items)
    hits = await retriever.retrieve(RetrievalQuery(text="Troponin raised", k=3))
    assert [(h.rank, h.item.id) for h in hits] == [(1, "e1"), (2, "p1"), (3, "e2")]
    assert [
        h.item.id
        for h in await retriever.retrieve(RetrievalQuery(text="troponin", origin="patient_document"))
    ] == ["p1"]
    assert len(await retriever.retrieve(RetrievalQuery(text="troponin", k=1))) == 1
    assert await retriever.retrieve(RetrievalQuery(text="zzz")) == []
    with pytest.raises(ValidationError):
        RetrievalQuery(text="x", k=0)


def claim(**kw: object) -> Claim:
    base: dict[str, object] = {
        "id": "c1",
        "text": "t",
        "kind": "external_evidence",
        "agent": "cardiology",
        "status": "supported",
        "rationale": "r",
        "patient_fact_ids": ["f1"],
        "external_source_ids": ["s1"],
    }
    return Claim.model_validate({**base, **kw})


def test_a_sound_claim_has_no_structural_problems() -> None:
    assert check_claim_structure(claim(), {"f1"}, {"s1"}) == []


def test_each_structural_problem_is_reported() -> None:
    assert "supported_without_citation" in check_claim_structure(
        claim(patient_fact_ids=[], external_source_ids=[]), set(), set()
    )
    assert "unknown_fact:f1" in check_claim_structure(claim(), set(), {"s1"})
    assert "unknown_source:s1" in check_claim_structure(claim(), {"f1"}, set())
    assert "external_claim_without_source" in check_claim_structure(
        claim(external_source_ids=[]), {"f1"}, set()
    )
    assert "removed_without_reason" in check_claim_structure(
        claim(status="insufficient_evidence", removed=True), {"f1"}, {"s1"}
    )
    assert "removed_but_supported" in check_claim_structure(
        claim(removed=True, removal_reason="x"), {"f1"}, {"s1"}
    )


@pytest.mark.parametrize("scenario", ["cardiology", "missing_info", "conflicting"])
def test_fixture_claims_cite_things_that_exist(scenario: str) -> None:
    data = EvidenceData.model_validate(json.loads((FIX / scenario / "evidence.json").read_text()))
    case = json.loads((FIX / scenario / "case.v1.json").read_text())
    facts = {v for v in _fact_refs(case)}
    sources = {s.id for s in data.sources}
    for c in data.claims:
        problems = check_claim_structure(
            c, facts | set(c.patient_fact_ids), sources
        )  # patient facts may live outside case.v1 refs
        assert [p for p in problems if not p.startswith("unknown_fact")] == [], (scenario, c.id)


def _fact_refs(node: object) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        out += [v for k, v in node.items() if k == "fact_ref" and isinstance(v, str)]
        for v in node.values():
            out += _fact_refs(v)
    elif isinstance(node, list):
        for v in node:
            out += _fact_refs(v)
    return out
