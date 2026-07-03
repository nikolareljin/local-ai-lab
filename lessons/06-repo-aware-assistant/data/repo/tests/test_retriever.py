"""Tests that cover the retriever: ranking order and tie-breaking."""

from retriever import rank, score


def test_score_counts_overlap():
    assert score({"reset", "password"}, {"reset", "link"}) == 1


def test_rank_orders_by_overlap_then_index():
    passages = make_passages()
    top = rank({"note", "search"}, passages, top_k=2)
    assert [p.index for p in top] == [0, 2]
