"""Tests that cover the retriever: ranking order and tie-breaking."""

from collections import namedtuple

from retriever import rank, score

Passage = namedtuple("Passage", ["index", "terms"])


def make_passages():
    """Three toy passages: the first and last match "note", the middle does not."""
    return [
        Passage(0, {"note", "search"}),
        Passage(1, {"reset", "password"}),
        Passage(2, {"note", "index"}),
    ]


def test_score_counts_overlap():
    assert score({"reset", "password"}, {"reset", "link"}) == 1


def test_rank_orders_by_overlap_then_index():
    passages = make_passages()
    top = rank({"note", "search"}, passages, top_k=2)
    assert [p.index for p in top] == [0, 2]
