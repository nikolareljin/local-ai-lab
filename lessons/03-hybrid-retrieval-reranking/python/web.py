"""Lesson 3 - interactive hybrid-search GUI (experiment locally).

Type a query and tune the knobs — BM25 `k1`/`b`, the RRF `k`, and the semantic
arm's synonyms — then watch the three rankings *and the numbers behind them*
change live. There is **nothing to edit**: the sliders feed the very same
`hybrid()` the one-shot `demo` and the test use, so what you see here is the real
algorithm, just made tweakable.

Run:  ./run -l 3        (or:  ./run -l 3 web)

The byte-checked `demo` action keeps using the tiny data/ corpus; this GUI searches
the richer 5-chapter story so hybrid retrieval is fun to feel on real prose.
"""

import math
import sys
from pathlib import Path

# Reach the shared GUI scaffold under tools/ (this file runs with cwd = the lesson
# dir, so locate the repo root from the file path, not the working directory).
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from lesson_web import serve  # the shared L1-style experiment GUI

from hybrid_demo import (
    B,
    K1,
    RRF_K,
    SYNONYMS,
    bm25_scores,
    rank,
    rrf,
    semantic_scores,
    tokenize,
)

STORY_DIR = Path(__file__).resolve().parent.parent / "story"


def load_story():
    docs = []
    for path in sorted(STORY_DIR.glob("*.md")):
        docs.append({"name": path.name, "tokens": tokenize(path.read_text(encoding="utf-8"))})
    return docs


DOCS = load_story()

# The knobs exposed in the GUI — defaults are the lesson's own constants, so the UI
# opens on exactly the behaviour the demo and test pin.
PARAMS = [
    {"name": "k1", "label": "BM25 · k1 — term-frequency saturation", "kind": "range",
     "min": 0.2, "max": 3.0, "step": 0.1, "default": K1},
    {"name": "b", "label": "BM25 · b — length normalisation", "kind": "range",
     "min": 0.0, "max": 1.0, "step": 0.05, "default": B},
    {"name": "rrf_k", "label": "RRF · k — rank-fusion damping", "kind": "range",
     "min": 1, "max": 120, "step": 1, "default": RRF_K},
    {"name": "synonyms", "label": "Semantic arm — expand synonyms", "kind": "toggle",
     "default": True},
]

# Examples chosen for the *story* corpus this GUI searches (the byte-checked demo
# uses the tiny data/ corpus, where "broken gadget" shows BM25 finding nothing).
EXAMPLES = [
    {"label": "Exact name (BM25 nails it)", "query": "Nuevo Edén"},
    {"label": "A star by name", "query": "Alpha Centauri"},
    {"label": "Paraphrase — who discovered it", "query": "who found the new planet"},
    {"label": "Paraphrase — the spacesuit chapter", "query": "how did they keep the turtle alive in space"},
]


def _idf(query_tokens, docs):
    """Per-query-term IDF — the same rare-term weighting `bm25_scores` uses inside,
    surfaced here so the GUI can show *why* one term outweighs another."""
    n = len(docs)
    df = {}
    for d in docs:
        for t in set(d["tokens"]):
            df[t] = df.get(t, 0) + 1
    return {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in set(query_tokens) if t in df}


def _why_blocks(q, bm, sem, lexical, semantic, rrf_k, synonyms):
    """Build the 'why' breakdown: the query as each arm sees it, then a per-document
    table of BM25/semantic scores, ranks, and the RRF contribution that fuses them."""
    idf = _idf(q, DOCS)
    expanded = set(q)
    for t in list(expanded):
        expanded.update(synonyms.get(t, []))
    lex_pos = {name: i for i, name in enumerate(lexical)}
    sem_pos = {name: i for i, name in enumerate(semantic)}

    qtokens = [
        {"text": t, "note": ("idf %.2f" % idf[t]) if t in idf else "not in corpus",
         "muted": t not in idf}
        for t in q
    ]
    blocks = [{"kind": "tokens",
               "title": "Query terms — BM25 weights each by IDF (rarer = stronger)",
               "items": qtokens}]

    if synonyms:
        syns = [{"text": s, "note": "← " + t, "muted": True}
                for t in q for s in synonyms.get(t, [])]
        blocks.append({"kind": "tokens",
                       "title": "Synonym expansions the semantic arm also searches for"
                                if syns else "No synonym expansions for this query",
                       "items": syns})
    else:
        blocks.append({"kind": "note",
                       "text": "Synonyms are OFF — the semantic arm now matches literal words only, "
                               "so it collapses toward BM25 and paraphrases stop being recovered."})

    columns = ["document", "BM25", "semantic", "BM25 rank", "sem rank", "RRF lex", "RRF sem", "fused RRF"]
    rows = []
    for i, d in enumerate(DOCS):
        name = d["name"]
        lr, sr = lex_pos.get(name), sem_pos.get(name)
        lex_rrf = 1.0 / (rrf_k + lr + 1) if lr is not None else 0.0
        sem_rrf = 1.0 / (rrf_k + sr + 1) if sr is not None else 0.0
        fused = lex_rrf + sem_rrf
        num_or_miss = lambda x, text: {"v": text, "cls": "num" if x else "miss"}
        rows.append((fused, [
            {"v": name, "cls": "text"},
            num_or_miss(bm[i] > 0, "%.3f" % bm[i]),
            num_or_miss(sem[i] > 0, "%.3f" % sem[i]),
            num_or_miss(lr is not None, ("#%d" % (lr + 1)) if lr is not None else "—"),
            num_or_miss(sr is not None, ("#%d" % (sr + 1)) if sr is not None else "—"),
            num_or_miss(lex_rrf, ("%.4f" % lex_rrf) if lex_rrf else "—"),
            num_or_miss(sem_rrf, ("%.4f" % sem_rrf) if sem_rrf else "—"),
            num_or_miss(fused, ("%.4f" % fused) if fused else "—"),
        ]))
    rows.sort(key=lambda r: -r[0])  # best fused first — the order the hybrid returns
    blocks.append({"kind": "table",
                   "title": "Why each document ranks where it does",
                   "columns": columns, "rows": [cells for _, cells in rows]})
    blocks.append({"kind": "note",
                   "text": "BM25 = Σ idf(term) · saturated term-frequency (shaped by k1 & b). "
                           "Semantic = overlap with the synonym-expanded query. RRF fuses by rank: "
                           "1/(k+rank) from each arm, summed. A blank means that arm didn't rank the "
                           "document — which is exactly how a paraphrase scores 0 on BM25 yet the "
                           "hybrid still answers via the semantic arm."})
    return blocks


def search(query, values):
    k1, b, rrf_k = values["k1"], values["b"], values["rrf_k"]
    synonyms = SYNONYMS if values["synonyms"] else {}
    if not query:
        return {"arms": [], "blocks": [{"kind": "note", "text": "Type a query — or pick an example above."}]}

    q = tokenize(query)
    bm = bm25_scores(q, DOCS, k1, b)
    sem = semantic_scores(q, DOCS, synonyms)
    lexical = rank(DOCS, bm)
    semantic = rank(DOCS, sem)
    fused = rrf([lexical, semantic], rrf_k)
    arms = [
        {"label": "BM25 (lexical)", "ranking": lexical},
        {"label": "Semantic (stand-in)", "ranking": semantic},
        {"label": "Hybrid (RRF)", "ranking": fused},
    ]
    return {"arms": arms, "blocks": _why_blocks(q, bm, sem, lexical, semantic, rrf_k, synonyms)}


def main():
    serve(
        title="Lesson 3 · Hybrid search — The Voyage of Caretta the Magnificent",
        subtitle="BM25 wins exact terms; the semantic stand-in wins paraphrases; RRF fuses both. "
                 "Tune the knobs and watch the rankings — and the numbers behind them — change live.",
        hint="Searching the bundled 5-chapter story. Try an exact name, then a paraphrase of it.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
