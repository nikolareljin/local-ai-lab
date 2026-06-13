"""Offline test for the Lesson 3 hybrid retrieval demo (Python).

Encodes the lesson's claim: BM25 wins the exact-term query, the semantic stand-in
wins the paraphrase query, and the hybrid (RRF) gets both right.

Run:  python -m pytest test_hybrid.py
"""

from hybrid_demo import hybrid, load_docs


def test_exact_term_query_favours_bm25():
    docs = load_docs()
    lexical, semantic, fused = hybrid("error E_4096", docs)
    # The exact error code lives only in error_codes.md, so BM25 nails it.
    assert lexical[0] == "error_codes.md"
    assert fused[0] == "error_codes.md"


def test_paraphrase_query_favours_semantic():
    docs = load_docs()
    lexical, semantic, fused = hybrid("my device won't turn on", docs)
    # "won't turn on" never appears verbatim; the semantic stand-in still finds
    # the power/startup doc, and the hybrid ranking agrees.
    assert semantic[0] == "power_issues.md"
    assert fused[0] == "power_issues.md"


def test_all_documents_ranked():
    docs = load_docs()
    lexical, semantic, fused = hybrid("error E_4096", docs)
    assert sorted(fused) == ["error_codes.md", "power_issues.md", "setup.md"]
