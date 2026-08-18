"""Lesson 7 - the hand-rolled pipeline, imported straight from Lesson 1.

Nothing here reimplements anything. Every step calls the module you wrote in
Lesson 1, so the comparison in `langchain_rag.py` is honest: it is your code on
one side and LangChain on the other, over the same corpus with the same prompt.

  load     -> localrag.extract.discover_files + extract_pages
  split    -> localrag.chunk.chunk_pages
  retrieve -> localrag.retriever.Bm25Retriever
  prompt   -> localrag.prompts.SYSTEM_PROMPT + build_user_prompt
  answer   -> localrag.providers.get_provider(...).chat(...)

The one thing this file adds is a `Config` pointed at the lesson's own corpus and
a throwaway cache directory, so running the lesson never touches the index under
your real `.localrag/`.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import List

# The course package lives four levels up (lessons/07-langchain-rag/python/ -> repo root).
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from localrag.chunk import Chunk, chunk_pages  # noqa: E402
from localrag.config import Config, load_config  # noqa: E402
from localrag.engine import dedup_sources  # noqa: E402
from localrag.extract import Page, discover_files, extract_pages  # noqa: E402
from localrag.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from localrag.providers import get_provider  # noqa: E402
from localrag.retriever import Bm25Retriever  # noqa: E402

LESSON_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = LESSON_DIR / "data" / "corpus"

NAME = "hand-rolled"

# The Lesson 1 files this pipeline is made of. `langchain_rag.py` counts their
# lines at runtime for the scorecard, so the numbers can never drift from reality.
COMPONENT_FILES = {
    "load": "localrag/extract.py",
    "split": "localrag/chunk.py",
    "index": "localrag/store.py",
    "retrieve": "localrag/retriever.py",
    "prompt": "localrag/prompts.py",
    "provider": "localrag/providers/__init__.py",
    "chain": "localrag/engine.py",
}


# One scratch cache for the whole process, cleaned up automatically when it exits.
# `mkdtemp` would leave a lesson7-* directory behind on every run, and this lesson
# gets run repeatedly while you experiment.
_SCRATCH = tempfile.TemporaryDirectory(prefix="lesson7-")


def lesson_config(provider: str | None = None) -> Config:
    """A Lesson 1 Config pointed at this lesson's corpus and a scratch cache.

    The cache directory is deliberately a throwaway: running the lesson must never
    touch the index under your real `.localrag/`.
    """
    config = load_config()
    config.docs_dir = CORPUS_DIR
    config.cache_dir = Path(_SCRATCH.name)
    if provider:
        config.provider = provider
    return config


def load(corpus_dir: Path = CORPUS_DIR) -> List[Page]:
    """extract.py - every supported file under the corpus, in sorted order."""
    pages: List[Page] = []
    for path in discover_files(corpus_dir):
        pages.extend(extract_pages(path))
    return pages


def split(pages: List[Page], size: int, overlap: int) -> List[Chunk]:
    """chunk.py - overlapping chunks that each remember source and page."""
    return chunk_pages(pages, size=size, overlap=overlap)


def build_retriever(chunks: List[Chunk]) -> Bm25Retriever:
    """retriever.py - build the BM25 index once, then answer many queries from it.

    Lesson 1 builds BM25 in `Bm25Retriever.__init__` and reuses it, and the LangChain
    arm does the same, so this arm must too. Rebuilding per query would tokenize the
    whole corpus on every question and make the comparison a measurement of who
    rebuilds their index more often.
    """
    return Bm25Retriever(chunks)


def retrieve(retriever: Bm25Retriever, question: str, k: int) -> List[Chunk]:
    """retriever.py - top-k chunks for one question, from an already-built index."""
    return retriever.search(question, k)


def sources(hits: List[Chunk]) -> List[str]:
    """engine.py - the `source:page` citations behind an answer."""
    return dedup_sources(hits)


def render_prompt(question: str, hits: List[Chunk]) -> tuple[str, str]:
    """prompts.py - the exact system and user strings the model will see."""
    return SYSTEM_PROMPT, build_user_prompt(question, hits)


def answer(config: Config, question: str, hits: List[Chunk]) -> str:
    """providers/ - call the configured provider with the grounded prompt."""
    system, user = render_prompt(question, hits)
    return get_provider(config.provider, config).chat(system, user)
