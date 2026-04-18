from __future__ import annotations

CHUNK_SIZE = 480
OVERLAP = 80


def chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + CHUNK_SIZE, n)
        chunk = text[i:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        i = end - OVERLAP
        if i < 0:
            i = 0
    return chunks
