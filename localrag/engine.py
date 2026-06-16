"""Shared query engine used by the web UI (and reusable elsewhere).

Keeps a cached retriever so repeated questions don't re-read and re-rank from
scratch, and rebuilds it when the docs folder changes or the retriever type is
switched. Thread-safe so the Flask dev server can handle concurrent requests.
"""

from __future__ import annotations

import threading
from typing import Dict, List

from .chunk import Chunk
from .config import Config
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .providers import get_provider
from .retriever import build_retriever
from .store import build_index, is_stale, load_chunks

_lock = threading.Lock()
_cache: Dict[str, object] = {"retriever": None, "key": None}


def refresh_index(config: Config) -> tuple[list[Chunk], int]:
    """Force a rebuild of the on-disk index and invalidate the retriever cache."""
    with _lock:
        chunks, n_files = build_index(config)
        _cache["retriever"] = None
        _cache["key"] = None
    return chunks, n_files


def get_retriever(config: Config):
    """Return a retriever for the current docs, rebuilding only when needed."""
    with _lock:
        if is_stale(config):
            build_index(config)
            _cache["retriever"] = None
        if _cache["retriever"] is None or _cache["key"] != config.retriever:
            chunks: List[Chunk] = load_chunks(config)
            _cache["retriever"] = build_retriever(chunks, config)
            _cache["key"] = config.retriever
        return _cache["retriever"]


def dedup_sources(hits: List[Chunk]) -> List[str]:
    seen: List[str] = []
    for h in hits:
        tag = f"{h['source']}:{h['page_number']}"
        if tag not in seen:
            seen.append(tag)
    return seen


def answer_question(config: Config, question: str) -> dict:
    """Retrieve grounding context, call the provider, and return a result dict."""
    retriever = get_retriever(config)
    hits = retriever.search(question, config.top_k)
    provider = get_provider(config.provider, config)
    answer = provider.chat(SYSTEM_PROMPT, build_user_prompt(question, hits))
    return {
        "answer": answer.strip(),
        "sources": dedup_sources(hits),
        "provider": config.provider,
        "retriever": getattr(retriever, "name", config.retriever),
        "num_hits": len(hits),
    }
