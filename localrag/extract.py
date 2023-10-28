"""Extract plain text from supported document types.

Returns a list of "pages": dicts with ``text``, ``page_number`` and ``source``.
For formats without real pages (DOCX/TXT/MD) the whole document is one page.
Mirrors the extraction approach used in document-tracker's document_processor,
trimmed down to the handful of formats this demo needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, TypedDict

SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


class Page(TypedDict):
    source: str
    page_number: int
    text: str


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _extract_pdf(path: Path) -> List[Page]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: List[Page] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(Page(source=path.name, page_number=i, text=text))
    return pages


def _extract_docx(path: Path) -> List[Page]:
    from docx import Document

    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if not text.strip():
        return []
    return [Page(source=path.name, page_number=1, text=text)]


def extract_pages(path: Path) -> List[Page]:
    """Extract text from a single file. Unsupported types return an empty list."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".docx":
        return _extract_docx(path)
    if ext in {".txt", ".md", ".markdown"}:
        text = _read_text_file(path).strip()
        return [Page(source=path.name, page_number=1, text=text)] if text else []
    return []


def discover_files(docs_dir: Path) -> List[Path]:
    """Find all supported files under the docs directory (recursively)."""
    if not docs_dir.exists():
        return []
    return sorted(
        p for p in docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )
