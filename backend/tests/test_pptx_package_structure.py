"""Strukturalna walidacja OOXML wygenerowanych PPTX.

Otwarcie w python-pptx / LibreOffice nie wystarcza — oba po cichu naprawiają błędy,
a Keynote odrzuca plik („Format pliku jest nieprawidłowy”).
"""
from __future__ import annotations

import base64
import io
import zipfile
from xml.etree import ElementTree as ET

import pytest

from teacher_helper.infrastructure.export import text_to_pptx
from teacher_helper.infrastructure.presentation_spec import spec_to_pptx_bytes

_NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
# Kolejność dzieci p:presentation wg schematu ECMA-376 (CT_Presentation)
_PRESENTATION_CHILD_ORDER = [
    "sldMasterIdLst", "notesMasterIdLst", "handoutMasterIdLst", "sldIdLst", "sldSz", "notesSz",
    "smartTags", "embeddedFontLst", "custShowLst", "photoAlbum", "custDataLst", "kinsoku",
    "defaultTextStyle", "modifyVerifier", "extLst",
]

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _spec_pptx() -> bytes:
    return spec_to_pptx_bytes(
        {
            "title": "Lekcja",
            "description": "Opis",
            "slides": [
                {"title": "Wstęp", "bullets": ["a", "b"], "speaker_notes": "Notatka 1"},
                {"title": "Obraz", "bullets": ["c"], "layout": "image_right", "speaker_notes": "Notatka 2"},
                {"title": "Porównanie", "bullets": ["x", "y", "z"], "layout": "comparison"},
            ],
        },
        slide_images={1: _PNG_1X1},
    )


def _text_pptx() -> bytes:
    return text_to_pptx("# Jeden\n- a\n- b\n## Dwa\n- c", "Tytuł")


def assert_valid_pptx_structure(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        pres = ET.fromstring(z.read("ppt/presentation.xml"))
        rels = ET.fromstring(z.read("ppt/_rels/presentation.xml.rels"))

    rels_by_type: dict[str, set[str]] = {}
    for rel in rels.findall("rel:Relationship", _NS):
        rels_by_type.setdefault(rel.get("Type", "").removeprefix(_RT), set()).add(rel.get("Id"))

    def ids(list_tag: str, item_tag: str) -> set[str]:
        return {el.get(_R_ID) for el in pres.findall(f"p:{list_tag}/p:{item_tag}", _NS)}

    assert ids("sldMasterIdLst", "sldMasterId") == rels_by_type.get("slideMaster", set())
    assert ids("sldIdLst", "sldId") == rels_by_type.get("slide", set())
    assert ids("notesMasterIdLst", "notesMasterId") == rels_by_type.get("notesMaster", set())
    assert len(pres.findall("p:notesMasterIdLst/p:notesMasterId", _NS)) <= 1

    order = [child.tag.split("}")[1] for child in pres]
    positions = [_PRESENTATION_CHILD_ORDER.index(tag) for tag in order]
    assert positions == sorted(positions), order

    sld_sz = pres.find("p:sldSz", _NS)
    assert sld_sz is not None
    assert (sld_sz.get("cx"), sld_sz.get("cy")) == ("12192000", "6858000")
    assert sld_sz.get("type") in (None, "custom")


@pytest.mark.parametrize("build", [_spec_pptx, _text_pptx])
def test_generated_pptx_has_consistent_ooxml_structure(build) -> None:
    assert_valid_pptx_structure(build())


def test_notes_master_is_registered_in_presentation_xml() -> None:
    with zipfile.ZipFile(io.BytesIO(_spec_pptx())) as z:
        assert "ppt/notesMasters/notesMaster1.xml" in z.namelist()
        pres = ET.fromstring(z.read("ppt/presentation.xml"))
    assert pres.find("p:notesMasterIdLst/p:notesMasterId", _NS) is not None


@pytest.mark.parametrize("build", [_spec_pptx, _text_pptx])
def test_font_formatting_is_set_on_runs_not_paragraph_defaults(build) -> None:
    with zipfile.ZipFile(io.BytesIO(build())) as z:
        slide_names = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
        slides = [ET.fromstring(z.read(n)) for n in slide_names]
    for slide in slides:
        assert slide.findall(".//a:pPr/a:defRPr", _NS) == []
    title_runs = [
        r
        for slide in slides
        for sp in slide.findall(".//p:sp", _NS)
        if (ph := sp.find(".//p:nvPr/p:ph", _NS)) is not None and ph.get("type") in ("title", "ctrTitle")
        for r in sp.findall(".//a:r/a:rPr", _NS)
    ]
    assert title_runs
    assert all(r.get("b") == "1" and r.get("sz") == "3200" for r in title_runs)
