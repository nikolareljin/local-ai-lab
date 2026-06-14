"""Offline test for the Lesson 3 hybrid retrieval demo (Python).

Encodes the lesson's claim: BM25 nails an exact term, but a keyword-free
paraphrase slips past BM25 entirely while the semantic stand-in recovers it —
and the hybrid (RRF) keeps the right answer either way.

Run:  python -m pytest test_hybrid.py
"""

import sys
from pathlib import Path

# Make the import work regardless of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hybrid_demo import hybrid, load_docs


def test_exact_term_query_favours_bm25():
    docs = load_docs()
    lexical, semantic, fused = hybrid("error E_4096", docs)
    # The exact error code lives only in error_codes.md, so BM25 nails it.
    assert lexical[0] == "error_codes.md"
    assert fused[0] == "error_codes.md"


def test_zero_score_docs_are_excluded():
    docs = load_docs()
    lexical, _, _ = hybrid("error E_4096", docs)
    # Only the document that actually matches is ranked — no zero-score filler.
    assert lexical == ["error_codes.md"]


def test_paraphrase_bm25_misses_semantic_recovers():
    docs = load_docs()
    lexical, semantic, fused = hybrid("broken gadget", docs)
    # No document contains "broken" or "gadget", so BM25 finds nothing...
    assert lexical == []
    # ...but the semantic stand-in maps broken -> fail/dead and recovers the doc,
    # and the hybrid keeps that hit.
    assert semantic[0] == "power_issues.md"
    assert fused[0] == "power_issues.md"
