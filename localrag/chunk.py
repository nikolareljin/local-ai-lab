"""Split extracted pages into overlapping chunks.

Roughly mirrors document-tracker's chunk_text: target size with overlap, and
break on a sentence/word boundary near the limit instead of mid-word. Each chunk
keeps its source + page so answers can cite where they came from.
"""

from __future__ import annotations

from typing import List, TypedDict

from .extract import Page


class Chunk(TypedDict):
    source: str
    page_number: int
    chunk_index: int
    text: str


def _split_text(text: str, size: int, overlap: int) -> List[str]:
    text = " ".join(text.split())  # normalize whitespace
    if len(text) <= size:
        return [text] if text else []

    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # Prefer to break on a sentence boundary, then a space, near the limit.
            window = text[start:end]
            for sep in (". ", "! ", "? ", "\n", " "):
                pos = window.rfind(sep)
                if pos > size // 2:
                    end = start + pos + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_pages(pages: List[Page], size: int = 1000, overlap: int = 200) -> List[Chunk]:
    chunks: List[Chunk] = []
    index = 0
    for page in pages:
        for piece in _split_text(page["text"], size, overlap):
            chunks.append(
                Chunk(
                    source=page["source"],
                    page_number=page["page_number"],
                    chunk_index=index,
                    text=piece,
                )
            )
            index += 1
    return chunks
