from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


SYNTHETIC_MARK = "SYNTHETIC TEST DOCUMENT / 실제 사용 불가"


def write_pdf_document(
    path: Path,
    *,
    title: str,
    fields: dict[str, Any],
    render_mode: str = "text",
    fingerprint_fields: dict[str, Any] | None = None,
    expected_readable: bool = True,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = _document_lines(title, fields, render_mode)
    if expected_readable:
        path.write_bytes(_build_pdf(lines, title=title, render_mode=render_mode))
    else:
        path.write_bytes(_build_corrupted_pdf(title, fields))

    content = path.read_bytes()
    fingerprint_text = _safe_normalized_text(_document_lines(title, fingerprint_fields or fields, render_mode))
    return {
        "content_hash": hashlib.sha256(content).hexdigest(),
        "text_fingerprint": hashlib.sha256(fingerprint_text.encode("utf-8")).hexdigest(),
        "perceptual_hash": hashlib.sha256(("visual:" + fingerprint_text).encode("utf-8")).hexdigest()[:32],
        "mime_type": "application/pdf",
        "file_size": len(content),
        "page_count": 1 if expected_readable else 0,
        "readable": expected_readable,
        "render_mode": render_mode,
    }


def pdf_readability(path: Path) -> bool:
    try:
        content = path.read_bytes()
    except OSError:
        return False
    return (
        content.startswith(b"%PDF-")
        and b"%%EOF" in content[-64:]
        and b"/Type /Page" in content
        and b"/Encrypt" not in content
    )


def normalized_fingerprint_for_fields(title: str, fields: dict[str, Any], render_mode: str) -> str:
    text = _safe_normalized_text(_document_lines(title, fields, render_mode))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _document_lines(title: str, fields: dict[str, Any], render_mode: str) -> list[str]:
    lines = [
        SYNTHETIC_MARK,
        f"DOCUMENT_TITLE: {title}",
        f"RENDER_MODE: {render_mode}",
    ]
    for key in sorted(fields):
        lines.append(f"{key}: {fields[key]}")
    return lines


def _build_pdf(lines: list[str], *, title: str, render_mode: str) -> bytes:
    scan_mode = render_mode.startswith("scan")
    text_commands = []
    if scan_mode:
        text_commands.extend(["q", "520 0 0 700 40 80 cm", "/Im1 Do", "Q"])
    text_commands.extend(["BT", "/F1 9 Tf", "50 790 Td"])
    for index, line in enumerate(lines):
        if index:
            text_commands.append("0 -14 Td")
        text_commands.append(f"({_escape_pdf_text(line)}) Tj")
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("utf-8")

    xobject_resource = " /XObject << /Im1 7 0 R >>" if scan_mode else ""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 4 0 R >>{xobject_resource} >> /Contents 5 0 R >>"
        ).encode("utf-8"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        (
            "<< /Title ({title}) /Subject (SYNTHETIC TEST DOCUMENT / actual use prohibited) "
            "/Author (Automated_Claims_Processing Data Generator) "
            "/Creator (data_generator) /Producer (data_generator) "
            "/CreationDate (D:20260101000000Z) /ModDate (D:20260101000000Z) >>"
        ).format(title=_escape_pdf_text(title)).encode("utf-8"),
    ]
    if scan_mode:
        image = _scan_image_bytes(title, render_mode)
        objects.append(
            b"<< /Type /XObject /Subtype /Image /Width 16 /Height 16 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length "
            + str(len(image)).encode("ascii")
            + b" >>\nstream\n"
            + image
            + b"\nendstream"
        )
    return _assemble_pdf(objects)


def _build_corrupted_pdf(title: str, fields: dict[str, Any]) -> bytes:
    text = "\n".join(
        [
            "%PDF-1.4",
            "% CORRUPTED OR PROTECTED SYNTHETIC TEST DOCUMENT",
            SYNTHETIC_MARK,
            f"DOCUMENT_TITLE: {title}",
            f"document_id: {fields.get('document_id', '')}",
        ]
    )
    return text.encode("utf-8")


def _assemble_pdf(objects: list[bytes]) -> bytes:
    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{index} 0 obj\n".encode("ascii"))
        chunks.append(body)
        chunks.append(b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    chunks.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        chunks.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    chunks.append(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return b"".join(chunks)


def _scan_image_bytes(title: str, render_mode: str) -> bytes:
    digest = hashlib.sha256(f"{title}|{render_mode}".encode("utf-8")).digest()
    pixels = bytearray()
    for y in range(16):
        for x in range(16):
            seed = digest[(x + y) % len(digest)]
            pixels.append(210 + ((seed + x * 3 + y * 5) % 35))
    return bytes(pixels)


def _escape_pdf_text(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _safe_normalized_text(lines: list[str]) -> str:
    text = "\n".join(lines).lower()
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return " ".join(text.split())


def _normalized_text(lines: list[str]) -> str:
    text = "\n".join(lines).lower()
    text = re.sub(r"[^a-z0-9가-힣]+", " ", text)
    return " ".join(text.split())
