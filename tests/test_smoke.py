"""Offline smoke test: extract -> chunk -> BM25 retrieve on the sample doc.

No network and no LLM. Proves the retrieval core works end to end.
"""

from pathlib import Path

from localrag.chunk import chunk_pages
from localrag.extract import extract_pages
from localrag.retriever import Bm25Retriever

SAMPLE = Path(__file__).resolve().parent.parent / "documents" / "sample_manual.md"


def _chunks():
    return chunk_pages(extract_pages(SAMPLE), size=400, overlap=80)


def test_extract_and_chunk():
    pages = extract_pages(SAMPLE)
    assert pages and pages[0]["source"] == "sample_manual.md"
    chunks = _chunks()
    assert len(chunks) >= 1
    assert all(c["text"] for c in chunks)


def test_bm25_finds_reset_instructions():
    chunks = _chunks()
    retriever = Bm25Retriever(chunks)
    hits = retriever.search("how do I reset the device", k=3)
    assert hits, "expected at least one BM25 hit"
    top = hits[0]["text"].lower()
    assert "reset" in top and "power button" in top


def test_retrieval_discriminates_between_topics():
    chunks = _chunks()
    retriever = Bm25Retriever(chunks)
    # A different question should surface a different top chunk.
    hits = retriever.search("how long does charging take", k=3)
    assert hits
    assert "charge" in hits[0]["text"].lower() or "usb-c" in hits[0]["text"].lower()


def test_search_respects_top_k():
    chunks = _chunks()
    retriever = Bm25Retriever(chunks)
    assert len(retriever.search("device", k=1)) <= 1
