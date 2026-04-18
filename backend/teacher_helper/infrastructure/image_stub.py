from __future__ import annotations

import struct
import zlib

from teacher_helper.use_cases.ports import ImageResult


class StubImageGenerator:
    """Zwraca minimalny PNG placeholder — do testów bez klucza API."""

    async def generate(
        self,
        prompt: str,
        style: str | None = None,
        size: str = "1024x1024",
    ) -> ImageResult:
        return ImageResult(
            image_data=_minimal_png(),
            mime_type="image/png",
            prompt_used=prompt,
            model="stub",
            revised_prompt=f"[STUB] {prompt[:200]}",
        )


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    c = chunk_type + data
    crc = zlib.crc32(c) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)


def _minimal_png() -> bytes:
    """Generuje minimalny prawidłowy plik PNG 1×1 (szary piksel)."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    raw_row = b"\x00\x80"
    idat_data = zlib.compress(raw_row)
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat_data)
        + _png_chunk(b"IEND", b"")
    )
