"""Lesson 3 - hybrid retrieval demo (Python).

BM25 (lexical) + a semantic stand-in, fused with Reciprocal Rank Fusion (RRF).
Dependency-free and offline: the same compact BM25 and the same synonym-expanded
"semantic" score are implemented identically in the Node and .NET ports, so all
three produce the same rankings.

Run:  python hybrid_demo.py

PRODUCTION (see the lesson README, "From demo to production"):
- replace the semantic stand-in with real sentence embeddings,
- add a cross-encoder reranker over the fused top-k.
"""

import math
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# BM25 parameters
K1 = 1.5
B = 0.75
# RRF constant
RRF_K = 60

# A few synonyms so the stand-in "semantic" arm matches paraphrases, the way real
# embeddings would. Kept identical across the Python, Node and .NET ports.
SYNONYMS = {
    "turn": ["power", "start", "startup", "boot"],
    "on": ["up"],
    "wont": ["fail", "fails", "cannot", "dead"],
    "broken": ["fail", "fails", "dead"],
}


def tokenize(text):
    return re.findall(r"[a-z0-9_]+", text.lower())


def load_docs():
    docs = []
    for path in sorted(DATA_DIR.glob("*.md")):
        docs.append({"name": path.name, "tokens": tokenize(path.read_text(encoding="utf-8"))})
    return docs


# --- Lexical arm: a compact BM25 (no external library) ----------------------
def bm25_scores(query_tokens, docs, k1=K1, b=B):
    n = len(docs)
    if n == 0:                      # empty corpus → no scores (avoid /0 on avgdl)
        return []
    avgdl = sum(len(d["tokens"]) for d in docs) / n
    df = {}
    for d in docs:
        for t in set(d["tokens"]):
            df[t] = df.get(t, 0) + 1
    scores = []
    for d in docs:
        dl = len(d["tokens"])
        score = 0.0
        for t in query_tokens:
            if t not in df:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            tf = d["tokens"].count(t)
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
        scores.append(score)
    return scores


# --- Semantic stand-in: synonym-expanded overlap (no model needed) ----------
def semantic_scores(query_tokens, docs, synonyms=SYNONYMS):
    q = set(query_tokens)
    for t in list(q):
        q.update(synonyms.get(t, []))
    scores = []
    for d in docs:
        toks = set(d["tokens"])
        scores.append(len(q & toks) / (len(q) or 1))
    return scores


def rank(docs, scores):
    """Best-first doc names, dropping zero-score (unmatched) docs so an arm that
    finds nothing contributes nothing to RRF. Deterministic: score desc, name asc."""
    order = sorted(range(len(docs)), key=lambda i: (-scores[i], docs[i]["name"]))
    return [docs[i]["name"] for i in order if scores[i] > 0]


def rrf(rankings, rrf_k=RRF_K):
    fused = {}
    for ranking in rankings:
        for pos, name in enumerate(ranking):
            fused[name] = fused.get(name, 0.0) + 1.0 / (rrf_k + pos + 1)
    return [name for name, _ in sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))]


def hybrid(query, docs, k1=K1, b=B, rrf_k=RRF_K, synonyms=SYNONYMS):
    q = tokenize(query)
    lexical = rank(docs, bm25_scores(q, docs, k1, b))
    semantic = rank(docs, semantic_scores(q, docs, synonyms))
    return lexical, semantic, rrf([lexical, semantic], rrf_k)


def main():
    docs = load_docs()
    for query in ["error E_4096", "broken gadget"]:
        lexical, semantic, fused = hybrid(query, docs)
        print(f'\nQuery: "{query}"')
        print(f"  BM25 (lexical):   {lexical}")
        print(f"  Semantic (stand): {semantic}")
        print(f"  Hybrid (RRF):     {fused}")


if __name__ == "__main__":
    main()
