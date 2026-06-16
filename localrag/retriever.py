"""Retrieval engines: BM25 (default, zero setup) and semantic embeddings.

Both expose the same ``search(query, k) -> list[Chunk]`` so the CLI never cares
which one is active. ``build_retriever`` selects by config and, importantly,
falls back to BM25 with a clear message if embeddings are requested but no embed
provider is reachable — the demo should never dead-end.
"""

from __future__ import annotations

import re
from typing import List, Optional, Protocol

from .chunk import Chunk
from .config import Config


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class Retriever(Protocol):
    def search(self, query: str, k: int) -> List[Chunk]:
        ...


class Bm25Retriever:
    name = "bm25"

    def __init__(self, chunks: List[Chunk]) -> None:
        from rank_bm25 import BM25Okapi

        self.chunks = chunks
        corpus = [_tokenize(c["text"]) for c in chunks] or [[""]]
        self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, k: int) -> List[Chunk]:
        # Empty corpus or non-positive k (k <= 0 would make top empty -> top[0] raises).
        if not self.chunks or k <= 0:
            return []
        scores = self.bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(self.chunks)), key=lambda i: scores[i], reverse=True)
        # Return the top-k candidates by score and let the grounding prompt judge
        # relevance. (BM25 IDF can be negative on tiny corpora, so an absolute
        # score cutoff would wrongly discard everything.) Only drop the long tail
        # that scores strictly worse than the best, when there is a real signal.
        top = ranked[:k]
        best = scores[top[0]]
        if best <= 0:
            return [self.chunks[i] for i in top]
        return [self.chunks[i] for i in top if scores[i] > 0]

    def peek(self, query: Optional[str] = None, k: int = 5) -> dict:
        """Expose the raw BM25 numbers behind the index — for the
        'How the system sees your data' view. Returns global index stats, one
        tokenized sample chunk, the most distinctive terms by IDF, and (if a
        query is given) the per-chunk scores with the query terms' IDF and
        term-frequencies that produced them.
        """
        bm = self.bm25
        n = len(self.chunks)
        idf = dict(getattr(bm, "idf", {}))
        top_terms = sorted(idf.items(), key=lambda kv: kv[1], reverse=True)[:18]

        sample = None
        if self.chunks:
            c0 = self.chunks[0]
            toks = _tokenize(c0["text"])
            sample = {
                "source": c0["source"],
                "page_number": c0["page_number"],
                "text_preview": c0["text"][:240],
                "num_tokens": len(toks),
                "tokens": toks[:48],
            }

        # With no real chunks the placeholder corpus would inflate the stats
        # (vocabulary/avg_doc_length/top_terms), so report zeros to stay
        # consistent with num_chunks == 0.
        out = {
            "retriever": "bm25",
            "params": {"k1": getattr(bm, "k1", None), "b": getattr(bm, "b", None)},
            "num_chunks": n,
            "vocabulary": len(idf) if n else 0,
            "avg_doc_length": round(float(getattr(bm, "avgdl", 0.0)), 2) if n else 0.0,
            "top_terms": (
                [{"term": t, "idf": round(float(v), 3)} for t, v in top_terms] if n else []
            ),
            "sample_chunk": sample,
        }

        query = (query or "").strip()
        if query and self.chunks:
            q_tokens = _tokenize(query)
            scores = bm.get_scores(q_tokens)
            ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)[:k]
            out["query"] = {
                "text": query,
                "tokens": q_tokens,
                "term_idf": {t: round(float(idf.get(t, 0.0)), 3) for t in q_tokens},
                "results": [
                    {
                        "source": self.chunks[i]["source"],
                        "page_number": self.chunks[i]["page_number"],
                        "score": round(float(scores[i]), 4),
                        "text_preview": self.chunks[i]["text"][:160],
                        "term_freqs": {t: int(bm.doc_freqs[i].get(t, 0)) for t in q_tokens},
                    }
                    for i in ranked
                ],
            }
        return out


class EmbeddingRetriever:
    name = "embeddings"

    def __init__(self, chunks: List[Chunk], config: Config) -> None:
        import numpy as np

        from . import store
        from .providers import embed_texts

        self.chunks = chunks
        self.config = config

        vectors = store.load_vectors(config)
        if vectors is None or len(vectors) != len(chunks):
            vectors = np.asarray(
                embed_texts(config.embed_provider, config, [c["text"] for c in chunks]),
                dtype="float32",
            )
            store.save_vectors(config, vectors)
        self._vectors = self._normalize(np.asarray(vectors, dtype="float32"))

    @staticmethod
    def _normalize(mat):
        import numpy as np

        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    def search(self, query: str, k: int) -> List[Chunk]:
        import numpy as np

        from .providers import embed_texts

        # Match Bm25Retriever: empty corpus or non-positive k yields no hits
        # (negative k would otherwise slice from the end and return most results).
        if not self.chunks or k <= 0:
            return []
        q = np.asarray(
            embed_texts(self.config.embed_provider, self.config, [query]), dtype="float32"
        )
        q = self._normalize(q)[0]
        sims = self._vectors @ q
        ranked = np.argsort(sims)[::-1][:k]
        return [self.chunks[i] for i in ranked]


def build_retriever(chunks: List[Chunk], config: Config) -> Retriever:
    """Pick a retriever from config, falling back to BM25 on embedding failure."""
    if config.retriever == "embeddings":
        try:
            return EmbeddingRetriever(chunks, config)
        except Exception as exc:  # provider unreachable / no key / import error
            print(
                f"[localrag] Embeddings unavailable ({exc}). Falling back to BM25.",
                flush=True,
            )
    return Bm25Retriever(chunks)
