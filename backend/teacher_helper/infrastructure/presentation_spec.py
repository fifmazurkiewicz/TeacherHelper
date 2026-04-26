"""Struktura prezentacji (JSON) → PPTX, odczyt PPTX/JSON, tekst do indeksu."""
from __future__ import annotations

import io
import json
import re
from typing import Any

# --- Normalizacja specyfikacji z LLM / z pliku JSON ---


def normalize_presentation_spec(data: Any) -> dict[str, Any] | None:
    """Waliduje i porządkuje słownik z modelu. Zwraca None, gdy brak slajdów merytorycznych."""
    if not isinstance(data, dict):
        return None
    title = (data.get("title") or "").strip() or "Prezentacja"
    desc = (data.get("description") or "").strip()
    slides_raw = data.get("slides")
    if not isinstance(slides_raw, list):
        return None
    out_slides: list[dict[str, Any]] = []
    for s in slides_raw:
        if not isinstance(s, dict):
            continue
        st = (s.get("title") or "").strip() or "Slajd"
        bullets = s.get("bullets")
        if not isinstance(bullets, list):
            bullets = []
        b_clean = [str(b).strip() for b in bullets if str(b).strip()]
        raw_img = s.get("image", None)
        inc = s.get("include_image")
        if inc is None:
            if raw_img is None:
                inc = False
            elif isinstance(raw_img, bool):
                inc = raw_img
            elif isinstance(raw_img, dict) and not raw_img:
                inc = False
            else:
                inc = True
        else:
            inc = bool(inc)
        image_hint: str | None = None
        if inc and isinstance(raw_img, dict):
            image_hint = (
                (raw_img.get("suggested_prompt") or raw_img.get("prompt") or "").strip() or None
            )
        elif inc and isinstance(raw_img, str) and raw_img.strip():
            image_hint = raw_img.strip()
        if not image_hint and isinstance(s.get("image_hint"), str) and s.get("image_hint", "").strip():
            image_hint = (s.get("image_hint") or "").strip()
        out_slides.append(
            {
                "title": st,
                "bullets": b_clean,
                "include_image": inc,
                "image_hint": image_hint,
            }
        )
    has_substance = bool(out_slides) or bool(desc and desc.strip()) or (title != "Prezentacja")
    if not has_substance:
        return None
    return {
        "version": 1,
        "title": title,
        "description": desc,
        "slides": out_slides,
    }


def parse_presentation_json(raw: str) -> dict[str, Any] | None:
    """Parsuje odpowiedź LLM (opcjonalnie w ```json)."""
    t = (raw or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if "```" in t:
            t = t.rsplit("```", 1)[0]
    try:
        data = json.loads(t)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{[\s\S]*\}\s*$", t)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        else:
            return None
    return normalize_presentation_spec(data)


def spec_to_json_text(spec: dict[str, Any]) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2)


# --- PPTX ---


def spec_to_pptx_bytes(spec: dict[str, Any]) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    title = (spec.get("title") or "Prezentacja")[:200]
    desc = (spec.get("description") or "")[:1200]
    # Slajd 1 — tytuł + opis
    layout0 = prs.slide_layouts[0]
    slide0 = prs.slides.add_slide(layout0)
    slide0.shapes.title.text = title
    if len(slide0.placeholders) > 1:
        ph = slide0.placeholders[1]
        ph.text = desc if desc else " "

    layout1 = prs.slide_layouts[1]
    for s in spec.get("slides") or []:
        if not isinstance(s, dict):
            continue
        st = (s.get("title") or "Slajd")[:200]
        bullets = s.get("bullets") or []
        body_lines: list[str] = list(bullets) if isinstance(bullets, list) else []
        if s.get("include_image"):
            hint = (s.get("image_hint") or "").strip()
            if hint:
                body_lines.append("")
                body_lines.append(f"[Propozycja grafiki: {hint}]")
            else:
                body_lines.append("")
                body_lines.append("(Miejsce na grafikę — uzupełnij w PowerPoint, jeśli potrzeba.)")
        slide = prs.slides.add_slide(layout1)
        slide.shapes.title.text = st
        body = slide.placeholders[1]
        tf = body.text_frame
        tf.clear()
        if not body_lines:
            p0 = tf.paragraphs[0]
            p0.text = " "
            p0.font.size = Pt(18)
        for i, line in enumerate(body_lines):
            if i == 0:
                p = tf.paragraphs[0]
                p.text = line
                p.font.size = Pt(18)
            else:
                p = tf.add_paragraph()
                p.text = line
                p.font.size = Pt(16 if line.startswith("[") or line.startswith("(") else 18)
                p.level = 0
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _shape_text(sh) -> str:
    try:
        if hasattr(sh, "text") and sh.text:
            return sh.text.strip()
    except Exception:
        pass
    return ""


def pptx_to_spec(data: bytes) -> dict[str, Any] | None:
    """Odczyt istniejącego PPTX do specyfikacji (edycja / kontynuacja)."""
    try:
        from pptx import Presentation
    except Exception:
        return None
    try:
        prs = Presentation(io.BytesIO(data))
    except Exception:
        return None
    if not prs.slides:
        return None
    s0 = prs.slides[0]
    title = _shape_text(s0.shapes.title) if s0.shapes.title else "Prezentacja"
    desc = ""
    if len(s0.shapes) > 1:
        for sh in s0.shapes:
            if sh == s0.shapes.title:
                continue
            t = _shape_text(sh)
            if t and t != title:
                desc = t
                break
    slides_out: list[dict[str, Any]] = []
    for idx in range(1, len(prs.slides)):
        sl = prs.slides[idx]
        st = _shape_text(sl.shapes.title) if sl.shapes.title else f"Slajd {idx + 1}"
        body_t = ""
        if len(sl.placeholders) > 1:
            try:
                body_t = _shape_text(sl.placeholders[1])
            except Exception:
                body_t = ""
        lines: list[str] = []
        include_image = bool(body_t) and (
            "[Propozycja grafiki:" in body_t or "Miejsce na grafikę" in body_t
        )
        image_hint: str | None = None
        if "[Propozycja grafiki:" in body_t and "]" in body_t:
            a = body_t.find("[Propozycja grafiki:")
            b = body_t.rfind("]")
            if a >= 0 and b > a:
                image_hint = body_t[a + len("[Propozycja grafiki:") : b].strip() or None
        for part in body_t.split("\n"):
            p = part.strip()
            if not p:
                continue
            if p.startswith("[Propozycja grafiki:") and p.endswith("]"):
                continue
            if p.startswith("(Miejsce na grafikę"):
                continue
            lines.append(p)
        slides_out.append(
            {
                "title": st,
                "bullets": lines,
                "include_image": include_image,
                "image_hint": image_hint,
            }
        )
    return normalize_presentation_spec(
        {"title": title, "description": desc, "slides": slides_out},
    )


def spec_to_readable_plan_text(spec: dict[str, Any]) -> str:
    """Czytelny opis planu (tytuł, opis, slajdy) — do pliku PDF i podglądu."""
    parts: list[str] = [f"# {spec.get('title', '')}", "", (spec.get("description") or "").strip(), ""]
    for i, s in enumerate(spec.get("slides") or [], start=1):
        st = s.get("title", "") if isinstance(s, dict) else ""
        parts.append(f"## Slajd {i + 1} — {st}")
        bullets = (s.get("bullets") or []) if isinstance(s, dict) else []
        if isinstance(bullets, list):
            for b in bullets:
                parts.append(f"- {b}")
        if isinstance(s, dict) and s.get("include_image"):
            h = (s.get("image_hint") or "").strip()
            if h:
                parts.append(f"  (propozycja grafiki: {h})")
            else:
                parts.append("  (miejsce na grafikę — opcjonalnie)")
        parts.append("")
    return "\n".join(parts).strip()


def extract_pptx_plain_text(data: bytes) -> str:
    """Treść PPTX do indeksu wyszukiwania / eksportu do PDF (tekstowo)."""
    spec = pptx_to_spec(data)
    if not spec:
        return ""
    return spec_to_readable_plan_text(spec)
