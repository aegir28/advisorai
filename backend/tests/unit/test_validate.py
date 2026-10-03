"""Upload validation: real type from bytes, size, hash, page count. No AI, no OCR."""

import hashlib
import io

import pytest
from pypdf import PdfWriter

from app.docintel.validate import MAX_BYTES, MAX_PDF_PAGES, sniff_mime, validate_upload

pytestmark = pytest.mark.anyio

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 20
JPEG = b"\xff\xd8\xff\xe0" + b"x" * 20


def make_pdf(pages: int = 1, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    if password:
        writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_sniffing_ignores_the_declared_type() -> None:
    assert sniff_mime(PNG) == "image/png"
    assert sniff_mime(JPEG) == "image/jpeg"
    assert sniff_mime(b"%PDF-1.7\n...") == "application/pdf"
    assert sniff_mime(b"junk\n%PDF-1.4") == "application/pdf"  # the spec allows leading bytes
    for other in (b"", b"MZ\x90\x00", b"GIF89a", b"<html>", b"PK\x03\x04"):
        assert sniff_mime(other) is None


async def test_a_valid_pdf_reports_pages_hash_and_size() -> None:
    data = make_pdf(4)
    result = await validate_upload(data, "application/pdf")
    assert result.verdict == "ok" and result.pages == 4 and result.note is None
    assert result.sha256 == hashlib.sha256(data).hexdigest() and result.size_bytes == len(data)


async def test_images_have_one_page() -> None:
    for data, mime in ((PNG, "image/png"), (JPEG, "image/jpeg")):
        result = await validate_upload(data, mime)
        assert result.verdict == "ok" and result.pages == 1 and result.mime_type == mime


@pytest.mark.parametrize(
    ("data", "declared", "fragment"),
    [
        (b"", "application/pdf", "empty"),
        (b"MZ" + b"0" * 50, "application/pdf", "Only PDF, JPG and PNG"),
        (PNG, "application/pdf", "does not match"),
        (make_pdf(), "image/jpeg", "does not match"),
        (b"%PDF-1.4 not really", "application/pdf", "could not open"),
        (make_pdf(password="x"), "application/pdf", "password protected"),
        (b"%PDF-" + b"0" * MAX_BYTES, "application/pdf", "20 MB"),
    ],
)
async def test_rejections_use_fixed_person_safe_notes(data: bytes, declared: str, fragment: str) -> None:
    result = await validate_upload(data, declared)
    assert result.verdict == "rejected" and result.note is not None and fragment in result.note
    assert result.pages is None and result.mime_type is None


async def test_a_pdf_with_too_many_pages_is_rejected() -> None:
    result = await validate_upload(make_pdf(MAX_PDF_PAGES + 1), "application/pdf")
    assert result.verdict == "rejected" and str(MAX_PDF_PAGES) in (result.note or "")
