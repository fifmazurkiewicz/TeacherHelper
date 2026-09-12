"""Konwersja treści plików do formatów eksportowych (PDF, DOCX, TXT, PPTX)."""
from __future__ import annotations

import io
import os
import platform
import re
from pathlib import Path

SUPPORTED_FORMATS = ("txt", "pdf", "docx", "pptx")


def text_to_txt(text: str) -> bytes:
    return text.encode("utf-8")


def _wrap_line_for_pdf(line: str, max_chars: int = 92) -> list[str]:
    """Dzieli linię na fragmenty mieszczące się w PDF (fpdf wywala się na jednym „słowie” szerzej niż strona)."""
    line = line.replace("\r", "").replace("\t", "    ")
    if len(line) <= max_chars:
        return [line] if line else [" "]
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        end = min(i + max_chars, n)
        if end < n:
            sp = line.rfind(" ", i + 1, end)
            if sp > i + 8:
                end = sp + 1
        chunk = line[i:end].rstrip()
        out.append(chunk if chunk else " ")
        if end <= i:
            end = i + 1
        i = end
    return out or [" "]


def text_to_pdf(text: str, title: str = "") -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()

    font_path = _find_unicode_font()
    if font_path:
        pdf.add_font("Unicode", "", font_path)
        pdf.set_font("Unicode", size=11)
    else:
        pdf.set_font("Helvetica", size=11)

    if title:
        pdf.set_font_size(16)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font_size(11)
        pdf.ln(3)

    for raw in text.split("\n"):
        for seg in _wrap_line_for_pdf(raw):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, seg if seg.strip() else " ", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())


def text_to_docx(text: str, title: str = "") -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(0x24, 0x2B, 0x38)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    for level, size, color in (
        (1, 22, (0x15, 0x3E, 0x75)),
        (2, 16, (0x0F, 0x76, 0x6E)),
        (3, 12, (0x33, 0x41, 0x55)),
    ):
        style = styles[f"Heading {level}"]
        style.font.name = "Aptos Display"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(*color)
        style.paragraph_format.space_before = Pt(12 if level > 1 else 0)
        style.paragraph_format.space_after = Pt(6)

    def add_runs(paragraph, value: str) -> None:
        """Render a small, predictable Markdown subset without leaking markers."""
        token_re = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|(?<!\*)\*[^*]+\*(?!\*)|`[^`]+`)")
        for part in token_re.split(value):
            if not part:
                continue
            run = paragraph.add_run()
            if (part.startswith("**") and part.endswith("**")) or (
                part.startswith("__") and part.endswith("__")
            ):
                run.text = part[2:-2]
                run.bold = True
            elif part.startswith("*") and part.endswith("*"):
                run.text = part[1:-1]
                run.italic = True
            elif part.startswith("`") and part.endswith("`"):
                run.text = part[1:-1]
                run.font.name = "Consolas"
                run.font.size = Pt(9.5)
                run.font.color.rgb = RGBColor(0x0F, 0x76, 0x6E)
            else:
                run.text = part

    if title:
        p = doc.add_paragraph()
        p.style = styles["Title"]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(title)
        r.font.name = "Aptos Display"
        r.font.size = Pt(26)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x15, 0x3E, 0x75)
        p.paragraph_format.space_after = Pt(4)
        accent = doc.add_paragraph()
        accent.paragraph_format.space_after = Pt(14)
        accent_run = accent.add_run("━━━━━━━━━━━━━━━━━━━━")
        accent_run.font.color.rgb = RGBColor(0x14, 0xB8, 0xA6)

    title_key = re.sub(r"\W+", "", title.casefold())
    first_content = True
    for raw in text.splitlines():
        value = raw.strip()
        if not value:
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", value)
        if heading:
            heading_text = heading.group(2).strip()
            heading_key = re.sub(r"\W+", "", heading_text.casefold())
            if first_content and title_key and heading_key == title_key:
                first_content = False
                continue
            p = doc.add_heading(level=len(heading.group(1)))
            add_runs(p, heading_text)
        elif value.startswith(("- ", "* ", "• ")):
            p = doc.add_paragraph(style="List Bullet")
            add_runs(p, value[2:].strip())
        elif re.match(r"^\d+[.)]\s+", value):
            p = doc.add_paragraph(style="List Number")
            add_runs(p, re.sub(r"^\d+[.)]\s+", "", value))
        elif value.startswith("> "):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.right_indent = Inches(0.15)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(8)
            add_runs(p, value[2:].strip())
            for run in p.runs:
                run.italic = True
                run.font.color.rgb = RGBColor(0x47, 0x55, 0x69)
            p_pr = p._p.get_or_add_pPr()
            borders = OxmlElement("w:pBdr")
            left = OxmlElement("w:left")
            left.set(qn("w:val"), "single")
            left.set(qn("w:sz"), "18")
            left.set(qn("w:color"), "14B8A6")
            borders.append(left)
            p_pr.append(borders)
        elif re.fullmatch(r"[-*_]{3,}", value):
            p = doc.add_paragraph("────────────────────────")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)
        else:
            p = doc.add_paragraph()
            add_runs(p, value)
        first_content = False

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run("TeacherHelper")
    run.font.name = "Aptos"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def text_to_pptx(text: str, title: str = "") -> bytes:
    """Generuje prezentację PPTX z tekstu markdown-like (nagłówki = slajdy)."""
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    slides_data = _parse_slides(text, title)

    for slide_title, bullets in slides_data:
        layout = prs.slide_layouts[1]  # Title and Content
        slide = prs.slides.add_slide(layout)

        slide.shapes.title.text = slide_title

        body = slide.placeholders[1]
        tf = body.text_frame
        tf.clear()

        for i, bullet in enumerate(bullets):
            if i == 0:
                tf.paragraphs[0].text = bullet
                tf.paragraphs[0].font.size = Pt(18)
            else:
                p = tf.add_paragraph()
                p.text = bullet
                p.font.size = Pt(18)

    if not slides_data:
        layout = prs.slide_layouts[0]  # Title Slide
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = title or "Prezentacja"
        if slide.placeholders[1]:
            slide.placeholders[1].text = text[:500]

    from teacher_helper.infrastructure.presentation_spec import apply_colorful_theme_to_presentation

    apply_colorful_theme_to_presentation(prs)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _parse_slides(text: str, fallback_title: str) -> list[tuple[str, list[str]]]:
    """Parsuje tekst na slajdy: nagłówki markdown (#/##) → tytuły, reszta → punktory."""
    slides: list[tuple[str, list[str]]] = []
    current_title = ""
    current_bullets: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        heading_match = re.match(r"^#{1,3}\s+(.+)$", stripped)
        if heading_match:
            if current_title or current_bullets:
                slides.append((current_title or fallback_title, current_bullets))
            current_title = heading_match.group(1).strip()
            current_bullets = []
        elif stripped.startswith(("- ", "* ", "• ")):
            current_bullets.append(stripped.lstrip("-*• ").strip())
        elif re.match(r"^\d+\.\s+", stripped):
            current_bullets.append(re.sub(r"^\d+\.\s+", "", stripped).strip())
        elif stripped:
            current_bullets.append(stripped)

    if current_title or current_bullets:
        slides.append((current_title or fallback_title, current_bullets))

    return slides


def convert_text(text: str, target_format: str, title: str = "") -> tuple[bytes, str]:
    """Konwertuje tekst do docelowego formatu. Zwraca (bytes, mime_type)."""
    fmt = target_format.lower().strip().lstrip(".")
    if fmt == "txt":
        return text_to_txt(text), "text/plain; charset=utf-8"
    if fmt == "pdf":
        return text_to_pdf(text, title), "application/pdf"
    if fmt == "docx":
        return text_to_docx(text, title), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    if fmt == "pptx":
        return text_to_pptx(text, title), (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    raise ValueError(f"Nieobsługiwany format eksportu: {fmt}. Dostępne: {', '.join(SUPPORTED_FORMATS)}")


def _find_unicode_font() -> str | None:
    """Szuka systemowej czcionki TTF ze wsparciem dla polskich znaków (Latin Extended itd.)."""
    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        base = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in (
            "arial.ttf",
            "calibri.ttf",
            "segoeui.ttf",
            "tahoma.ttf",
            "verdana.ttf",
            "micross.ttf",
        ):
            candidates.append(base / name)
    elif system == "Darwin":
        candidates = [
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Tahoma.ttf"),
        ]
    else:
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
            Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/liberation/LiberationSans-Regular.ttf"),
        ]
    for p in candidates:
        if p.is_file():
            return str(p)
    # Ostatnia deska: płytkie wyszukiwanie w typowych katalogach (np. WSL / niestandardowa instalacja)
    if system != "Windows":
        for root in (
            Path("/usr/share/fonts/truetype"),
            Path("/usr/share/fonts/TTF"),
        ):
            if not root.is_dir():
                continue
            try:
                for p in root.rglob("DejaVuSans.ttf"):
                    if p.is_file():
                        return str(p)
                for p in root.rglob("LiberationSans-Regular.ttf"):
                    if p.is_file():
                        return str(p)
            except OSError:
                continue
    return None
