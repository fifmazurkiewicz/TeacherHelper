from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET


def extract_plain_text(data: bytes, mime: str, filename: str) -> str:
    """Wyodrębnia tekst do indeksowania (PDF / DOCX / TXT / JSON / prosty odczyt)."""
    name = filename.lower()
    mime_l = (mime or "").lower()
    if "application/json" in mime or name.endswith(".json"):
        return data.decode("utf-8", errors="replace")
    if mime == "text/plain" or name.endswith(".txt") or name.endswith(".md"):
        return data.decode("utf-8", errors="replace")
    if mime_l == "application/pdf" or name.endswith(".pdf"):
        return _pdf_to_text(data)
    if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or name.endswith(
        ".docx"
    ):
        return _docx_to_text(data)
    return ""


def _pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t and t.strip():
                parts.append(t)
        return "\n".join(parts)
    except Exception:
        return ""


def _docx_to_text(data: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return _docx_xml_fallback(data)


def _docx_xml_fallback(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            with zf.open("word/document.xml") as f:
                xml = f.read()
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        texts = [t.text or "" for t in root.findall(".//w:t", ns)]
        return "".join(texts)
    except Exception:
        return ""
