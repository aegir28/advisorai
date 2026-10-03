"""Document intelligence: validation, text extraction, metadata, classification/extraction contracts, provenance.
All inputs are synthetic (tests/fixtures/docintel). No OCR and no model is involved."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.docintel.contracts import (
    DocumentClassification,
    DocumentText,
    EntityMention,
    ExtractedFact,
    ExtractionBatch,
    PageText,
    drop_unverified,
    verify_provenance,
)
from app.docintel.extract import ExtractionError, PypdfTextExtractor, StaticTextExtractor, build_metadata
from app.docintel.validate import validate_upload
from app.schemas.common import SourceRef
from tests.docs_support import make_pdf

pytestmark = pytest.mark.anyio
FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "docintel" / "synthetic_documents.json").read_text()
)
DOCS: dict[str, Any] = FIXTURE["documents"]


def batch_for(doc_id: str) -> ExtractionBatch:
    facts = []
    for f in DOCS[doc_id]["facts"]:
        optional = {k: f[k] for k in ("value", "unit") if k in f}  # optional means absent, never null
        facts.append(
            ExtractedFact(
                id=f["id"],
                doc_id=doc_id,
                category=f["category"],
                text=f["text"],
                entities=[EntityMention(type=f["entity"]["type"], text=f["entity"]["text"])],
                confidence="high",
                source=SourceRef(doc_id=doc_id, page=f["page"], snippet=f["snippet"]),
                **optional,
            )
        )
    return ExtractionBatch(doc_id=doc_id, facts=facts)


async def text_for(doc_id: str) -> DocumentText:
    return await StaticTextExtractor({k: v["pages"] for k, v in DOCS.items()}).extract(
        b"", "application/pdf", doc_id
    )


# ── extraction ─────────────────────────────────────────────────────────────────────────────────────
async def test_pypdf_extracts_the_text_layer_page_by_page() -> None:
    data = make_pdf(DOCS["d_lab"]["pages"])
    text = await PypdfTextExtractor().extract(data, "application/pdf", "d_lab")
    assert [p.page for p in text.pages] == [1, 2] and text.text_layer == "full"
    assert "Troponin I: 182 ng/L" in text.pages[0].text and "LDL cholesterol: 142 mg/dL" in text.pages[1].text
    assert text.extractor == "pypdf-text-layer"


async def test_a_scan_like_page_has_no_text_layer_and_is_reported_not_guessed() -> None:
    text = await PypdfTextExtractor().extract(make_pdf(["has text", ""]), "application/pdf", "d")
    assert [p.has_text_layer for p in text.pages] == [True, False] and text.text_layer == "partial"
    only_image = await PypdfTextExtractor().extract(b"\x89PNG", "image/png", "img")
    assert only_image.text_layer == "none" and only_image.pages[0].text == ""


@pytest.mark.parametrize("data", [b"not a pdf", b"%PDF-1.4 truncated"])
async def test_an_unreadable_pdf_raises_a_coded_error_without_leaking_content(data: bytes) -> None:
    with pytest.raises(ExtractionError) as exc:
        await PypdfTextExtractor().extract(data, "application/pdf", "d")
    assert str(exc.value) in {"pdf_unreadable", "pdf_empty"}


async def test_metadata_combines_validation_and_extraction() -> None:
    data = make_pdf(DOCS["d_lab"]["pages"])
    validation = await validate_upload(data, "application/pdf")
    text = await PypdfTextExtractor().extract(data, "application/pdf", "d_lab")
    meta = build_metadata("d_lab", validation, text)
    assert (meta.page_count, meta.text_layer, meta.needs_ocr, meta.mime_type) == (
        2,
        "full",
        False,
        "application/pdf",
    )
    assert meta.sha256 == validation.sha256 and meta.size_bytes == len(data)


async def test_metadata_flags_the_ocr_gap_for_a_partly_scanned_document() -> None:
    data = make_pdf(["text", ""])
    meta = build_metadata(
        "d",
        await validate_upload(data, "application/pdf"),
        await PypdfTextExtractor().extract(data, "application/pdf", "d"),
    )
    assert meta.needs_ocr is True and meta.text_layer == "partial"


async def test_metadata_refuses_a_document_that_failed_validation() -> None:
    rejected = await validate_upload(b"", "application/pdf")
    with pytest.raises(ExtractionError, match="document_not_validated"):
        build_metadata("d", rejected, await text_for("d_lab"))


# ── contracts ──────────────────────────────────────────────────────────────────────────────────────
def test_document_text_layer_levels() -> None:
    def doc(*layers: bool) -> DocumentText:
        return DocumentText(
            doc_id="d",
            pages=[
                PageText(page=i, text="t" if h else "", has_text_layer=h) for i, h in enumerate(layers, 1)
            ],
            extractor="x",
        )

    assert doc(True, True).text_layer == "full"
    assert doc(True, False).text_layer == "partial"
    assert doc(False).text_layer == "none"
    assert DocumentText(doc_id="d", pages=[], extractor="x").text_layer == "none"


def test_classification_uses_the_documented_document_types_and_cites_evidence() -> None:
    ok = DocumentClassification(
        doc_id="d",
        document_type="lab",
        confidence="high",
        evidence=[SourceRef(doc_id="d", page=1, snippet="LAB")],
    )
    assert ok.document_type == "lab"
    with pytest.raises(ValidationError):
        DocumentClassification.model_validate(
            {"doc_id": "d", "document_type": "xray", "confidence": "high", "evidence": []}
        )


def test_extraction_contracts_are_strict() -> None:
    fact = batch_for("d_lab").facts[0].model_dump()
    with pytest.raises(ValidationError):
        ExtractedFact.model_validate({**fact, "surprise": 1})
    with pytest.raises(ValidationError):
        ExtractedFact.model_validate({**fact, "category": "diagnosis_guess"})
    with pytest.raises(ValidationError):
        ExtractedFact.model_validate({k: v for k, v in fact.items() if k != "source"})


# ── provenance ─────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("doc_id", ["d_lab", "d_rx"])
async def test_every_fixture_fact_is_traceable_to_its_page(doc_id: str) -> None:
    report = verify_provenance(batch_for(doc_id), await text_for(doc_id))
    assert report.all_verified and report.unverified_ids == []


async def test_provenance_is_insensitive_to_case_and_whitespace_only() -> None:
    document = await text_for("d_lab")
    fact = batch_for("d_lab").facts[0]
    loose = fact.model_copy(
        update={"source": fact.source.model_copy(update={"snippet": "troponin   i:\n182 NG/L"})}
    )
    assert verify_provenance(ExtractionBatch(doc_id="d_lab", facts=[loose]), document).all_verified


async def test_a_fact_that_cannot_be_traced_is_flagged_and_dropped() -> None:
    document = await text_for("d_lab")
    good = batch_for("d_lab").facts
    invented = good[0].model_copy(
        update={"id": "bad1", "source": good[0].source.model_copy(update={"snippet": "Troponin I: 999 ng/L"})}
    )
    wrong_page = good[0].model_copy(
        update={"id": "bad2", "source": good[0].source.model_copy(update={"page": 2})}
    )
    missing_page = good[0].model_copy(
        update={"id": "bad3", "source": good[0].source.model_copy(update={"page": 9})}
    )
    other_doc = good[0].model_copy(update={"id": "bad4", "doc_id": "d_rx"})
    batch = ExtractionBatch(doc_id="d_lab", facts=[*good, invented, wrong_page, missing_page, other_doc])
    report = verify_provenance(batch, document)
    assert report.verdicts["bad1"] == "snippet_not_found"
    assert report.verdicts["bad2"] == "snippet_not_found"
    assert report.verdicts["bad3"] == "page_missing"
    assert report.verdicts["bad4"] == "wrong_document"
    assert report.unverified_ids == ["bad1", "bad2", "bad3", "bad4"]
    assert [f.id for f in drop_unverified(batch, report).facts] == ["x1", "x2", "x3"]
