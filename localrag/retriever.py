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
        if not self.chunks:
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

        if not self.chunks:
            return []
        q = np.asarray(embed_texts(self.config.embed_provider, self.config, [query]), dtype="float32")
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
