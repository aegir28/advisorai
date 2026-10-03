"""Build tiny valid PDFs with a real text layer, for tests. No dependency beyond the standard library."""


def make_pdf(pages: list[str]) -> bytes:
    """One PDF page per string. An empty string makes a page with no text layer (like a scan)."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    pages_obj_index = len(objects) + 1 + 2 * len(pages)  # id of the Pages object, known in advance
    for text in pages:
        lines = [ln for ln in text.split("\n") if ln]
        ops = (
            b"BT /F1 12 Tf 50 750 Td 14 TL "
            + b" ".join(
                b"("
                + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")
                + b") Tj T*"
                for ln in lines
            )
            + b" ET"
        )
        stream = add(b"<< /Length " + str(len(ops)).encode() + b" >>\nstream\n" + ops + b"\nendstream")
        page_ids.append(
            add(
                f"<< /Type /Page /Parent {pages_obj_index} 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {stream} 0 R >>".encode()
            )
        )
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    pages_id = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())
    assert pages_id == pages_obj_index
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
