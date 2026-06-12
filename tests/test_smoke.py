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


def test_search_guards_nonpositive_k():
    # k <= 0 must not raise (an empty top list would IndexError on top[0]).
    retriever = Bm25Retriever(_chunks())
    assert retriever.search("device", k=0) == []
    assert retriever.search("device", k=-3) == []


def test_config_clamps_invalid_top_k(monkeypatch):
    from localrag.config import load_config

    for bad in ("0", "-2", "not-a-number"):
        monkeypatch.setenv("RAG_TOP_K", bad)
        assert load_config().top_k == 5


def test_peek_shape_and_determinism():
    # Guards the /api/peek JSON shape shared by the Python, Node and C# ports.
    chunks = _chunks()
    retriever = Bm25Retriever(chunks)

    base = retriever.peek()
    assert base["retriever"] == "bm25"
    assert base["params"] == {"k1": 1.5, "b": 0.75}
    assert base["num_chunks"] == len(chunks)
    assert base["vocabulary"] > 0
    assert base["avg_doc_length"] > 0
    assert base["top_terms"] and {"term", "idf"} <= set(base["top_terms"][0])
    sample = base["sample_chunk"]
    assert {"source", "page_number", "text_preview", "num_tokens", "tokens"} <= set(sample)
    # No query given -> no per-query scoring block.
    assert "query" not in base

    result = retriever.peek("how do I reset the device", k=3)
    q = result["query"]
    assert q["text"] == "how do I reset the device"
    assert q["tokens"] and all(t in q["term_idf"] for t in q["tokens"])
    assert 1 <= len(q["results"]) <= 3
    row = q["results"][0]
    assert {"source", "page_number", "score", "text_preview", "term_freqs"} <= set(row)
    # Deterministic for the same query.
    assert retriever.peek("how do I reset the device", k=3) == result
