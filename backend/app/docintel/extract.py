"""Text extraction: the local, no-AI, no-OCR implementations of `TextExtractor`.

* `PypdfTextExtractor` reads the text layer of a PDF with pypdf (already a dependency). A page with no text
  layer (a scan) comes back empty with `has_text_layer=False`: reading it needs OCR, which is not built.
* `StaticTextExtractor` serves fixed text keyed by document id, for tests and demos.

Extracted text is the content of a medical record. It is returned to the caller and never logged.
"""

import asyncio
from io import BytesIO

from pypdf import PdfReader

from app.docintel.contracts import DocumentMetadata, DocumentText, PageText
from app.docintel.validate import ValidationResult


class ExtractionError(Exception):
    """The file could not be read. The message is a fixed code, never document content."""


def _extract_pdf(data: bytes, doc_id: str) -> DocumentText:
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("pdf_encrypted")
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            pages.append(PageText(page=number, text=text, has_text_layer=bool(text)))
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("pdf_unreadable") from exc
    if not pages:
        raise ExtractionError("pdf_empty")
    return DocumentText(doc_id=doc_id, pages=pages, extractor="pypdf-text-layer")


class PypdfTextExtractor:
    async def extract(self, data: bytes, mime_type: str, doc_id: str) -> DocumentText:
        if mime_type == "application/pdf":
            return await asyncio.to_thread(_extract_pdf, data, doc_id)
        # An image is one page with no text layer until OCR exists.
        return DocumentText(
            doc_id=doc_id, pages=[PageText(page=1, text="", has_text_layer=False)], extractor="image-no-ocr"
        )


class StaticTextExtractor:
    def __init__(self, pages_by_doc: dict[str, list[str]]) -> None:
        self._pages = pages_by_doc

    async def extract(self, data: bytes, mime_type: str, doc_id: str) -> DocumentText:
        del data, mime_type
        pages = self._pages.get(doc_id)
        if pages is None:
            raise ExtractionError("document_unknown")
        return DocumentText(
            doc_id=doc_id,
            pages=[
                PageText(page=i, text=t, has_text_layer=bool(t.strip())) for i, t in enumerate(pages, start=1)
            ],
            extractor="static-fixture",
        )


def build_metadata(doc_id: str, validation: ValidationResult, text: DocumentText) -> DocumentMetadata:
    """Combine upload validation (type, size, hash, pages) with what extraction found."""
    if validation.verdict != "ok" or validation.mime_type is None or validation.sha256 is None:
        raise ExtractionError("document_not_validated")
    layer = text.text_layer
    return DocumentMetadata(
        doc_id=doc_id,
        mime_type=validation.mime_type,
        size_bytes=validation.size_bytes,
        sha256=validation.sha256,
        page_count=max(len(text.pages), 1),
        text_layer=layer,
        needs_ocr=layer != "full",
    )
