"""Upload validation: size, real file type (magic bytes), content hash and page count.

This is document validation only. It does NOT read, OCR, classify or interpret what is in the file; that
is the later extraction phase. Nothing here talks to a network or an AI service, and none of the file's
content is logged: the result carries only technical facts and a fixed, person-safe note.

Why sniff the bytes: the browser-declared type (and the file name) are untrusted input. The storage bucket
only checks the declared Content-Type, so the backend checks the content itself.
"""

import asyncio
import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Final, Literal

from pypdf import PdfReader

MAX_BYTES: Final = 20 * 1024 * 1024
MAX_PDF_PAGES: Final = 300

Mime = Literal["application/pdf", "image/jpeg", "image/png"]
Verdict = Literal["ok", "rejected"]

_PNG: Final = b"\x89PNG\r\n\x1a\n"
_JPEG: Final = b"\xff\xd8\xff"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    verdict: Verdict
    size_bytes: int
    sha256: str | None
    mime_type: Mime | None
    pages: int | None
    # Fixed, person-safe text shown on the document card. Never derived from the file's content.
    note: str | None


def sniff_mime(head: bytes) -> Mime | None:
    """The real type from the first bytes, or None when it is not a PDF, JPEG or PNG."""
    if head.startswith(_PNG):
        return "image/png"
    if head.startswith(_JPEG):
        return "image/jpeg"
    # A PDF may have a few bytes of junk before the header; the spec allows the first 1024.
    if b"%PDF-" in head[:1024]:
        return "application/pdf"
    return None


def _count_pdf_pages(data: bytes) -> tuple[int | None, str | None]:
    """(pages, problem). A problem is a fixed message; the parser's own text is never forwarded."""
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            return None, "This PDF is password protected. Please upload an unlocked copy."
        pages = len(reader.pages)
    except Exception:
        return None, "We could not open this PDF. It may be damaged. Please upload another copy."
    if pages < 1:
        return None, "This PDF has no pages."
    if pages > MAX_PDF_PAGES:
        return None, f"This PDF has more than {MAX_PDF_PAGES} pages. Please upload the relevant pages."
    return pages, None


def _reject(size: int, sha256: str | None, note: str) -> ValidationResult:
    return ValidationResult("rejected", size, sha256, None, None, note)


def _validate(data: bytes, declared: str) -> ValidationResult:
    size = len(data)
    if size == 0:
        return _reject(0, None, "This file is empty.")
    if size > MAX_BYTES:
        return _reject(size, None, "This file is larger than 20 MB.")
    digest = hashlib.sha256(data).hexdigest()
    actual = sniff_mime(data[:1024])
    if actual is None:
        return _reject(size, digest, "Only PDF, JPG and PNG files are supported.")
    if actual != declared:
        return _reject(size, digest, "The file does not match the type it was uploaded as.")
    if actual == "application/pdf":
        pages, problem = _count_pdf_pages(data)
        if problem is not None:
            return _reject(size, digest, problem)
        return ValidationResult("ok", size, digest, actual, pages, None)
    return ValidationResult("ok", size, digest, actual, 1, None)


async def validate_upload(data: bytes, declared_mime: str) -> ValidationResult:
    """Validate downloaded upload bytes. CPU-bound parsing runs off the event loop."""
    return await asyncio.to_thread(_validate, data, declared_mime)
