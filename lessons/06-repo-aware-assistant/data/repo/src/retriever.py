"""Rank passages against a query by keyword overlap."""


def score(query_terms, passage_terms):
    """How many distinct query terms the passage contains."""
    return len(query_terms & passage_terms)


def rank(query, passages, top_k):
    """Return the top_k passages, highest overlap first, ties broken by order."""
    scored = [(score(query, p.terms), p) for p in passages]
    scored = [(s, p) for s, p in scored if s > 0]
    scored.sort(key=lambda sp: (-sp[0], sp[1].index))
    return [p for _, p in scored[:top_k]]
