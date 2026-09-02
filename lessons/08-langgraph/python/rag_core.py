"""Lesson 8 - the retrieval half, imported straight from Lesson 1.

Nothing here reimplements anything. Every step calls the module you wrote in
Lesson 1, exactly as Lesson 7 did, so all three arms in this lesson - the linear
chain, the `while` loop, and the LangGraph graph - are arguing about *control
flow* and nothing else:

  load     -> localrag.extract.discover_files + extract_pages
  split    -> localrag.chunk.chunk_pages
  retrieve -> localrag.retriever.Bm25Retriever
  prompt   -> localrag.prompts.SYSTEM_PROMPT + build_user_prompt
  cite     -> localrag.engine.dedup_sources
  answer   -> localrag.providers.get_provider(...).chat(...)

The corpus is Lesson 7's, by path - not a copy. The comparison in this lesson
only means something if the documents are literally the same bytes Lesson 7 used,
and a copy would drift the first time either lesson was edited. A reference
cannot. `test_corpus_is_lesson_sevens` pins it.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

# Walk out to the repo root so `localrag` is importable:
#   this file -> python -> 08-langgraph -> lessons -> repo root
# parents is 0-indexed, so the repo root is parents[3].
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
DATA_DIR = LESSON_DIR / "data"

# Lesson 7's corpus, by path. See the module docstring for why this is not a copy.
CORPUS_DIR = ROOT / "lessons" / "07-langchain-rag" / "data" / "corpus"

# One scratch cache for the whole process, cleaned up when it exits. Running a
# lesson must never touch the index under your real `.localrag/`.
_SCRATCH = tempfile.TemporaryDirectory(prefix="lesson8-")

# The same tokenizer BM25 uses, so "did the evidence cover this term?" is asked in
# the same vocabulary the retriever ranked in. Using a different one here would
# make the grader disagree with the retriever for reasons neither could explain.
_WORD = re.compile(r"[a-z0-9]+")

# Words carrying no retrieval signal. Kept deliberately short: this is a teaching
# stop-list, not a linguistic one, and every word in it is here because it showed
# up in one of the nine questions.
STOPWORDS = frozenset("""
a an and any are as at be but by can do does for from has have how i if in is
it its me my no not of on or so that the their them then there they this to was
what when where which who why will with you your
""".split())


def tokens(text: str) -> List[str]:
    """Lowercase word tokens, exactly as `localrag.retriever` tokenizes."""
    return _WORD.findall(text.lower())


def content_terms(text: str) -> List[str]:
    """The distinct meaning-carrying tokens of a query, in order of first use."""
    seen: List[str] = []
    for t in tokens(text):
        if t not in STOPWORDS and t not in seen:
            seen.append(t)
    return seen


def load_questions() -> dict:
    """The lesson's settings and its nine questions, from `data/questions.json`."""
    return json.loads((DATA_DIR / "questions.json").read_text(encoding="utf-8"))


def load_glossary() -> Dict[str, List[str]]:
    """The deterministic rewriter's vocabulary, minus the `_comment` key."""
    raw = json.loads((DATA_DIR / "glossary.json").read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def lesson_config(provider: str | None = None) -> Config:
    """A Lesson 1 Config pointed at Lesson 7's corpus and a throwaway cache."""
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


def build_retriever(size: int, overlap: int) -> Bm25Retriever:
    """Build the BM25 index once, for the whole run.

    Every arm is handed the *same* retriever object. Rebuilding per arm would
    re-tokenize the corpus each time and turn the comparison into a measurement of
    who rebuilds their index more often.
    """
    return Bm25Retriever(split(load(), size, overlap))


def retrieve(retriever: Bm25Retriever, query: str, k: int) -> List[Chunk]:
    """retriever.py - top-k chunks for one query, from an already-built index."""
    return retriever.search(query, k)


def sources(hits: List[Chunk]) -> List[str]:
    """engine.py - the `source:page` citations behind an answer."""
    return dedup_sources(hits)


def evidence_text(hits: List[Chunk]) -> str:
    """Everything the grader is allowed to look at: the retrieved text, and no more."""
    return "\n\n".join(h["text"] for h in hits)


def render_prompt(question: str, hits: List[Chunk]) -> Tuple[str, str]:
    """prompts.py - the exact system and user strings the model will see."""
    return SYSTEM_PROMPT, build_user_prompt(question, hits)


def answer(config: Config, question: str, hits: List[Chunk]) -> str:
    """providers/ - call the configured provider with the grounded prompt."""
    system, user = render_prompt(question, hits)
    return get_provider(config.provider, config).chat(system, user)


# The refusal Lesson 1 uses when the documents do not cover a question. Reused
# rather than reworded: an agent that gives up should sound exactly like the
# pipeline that gives up, or the reader learns two different failure modes.
ABSTAIN_TEXT = (
    "I could not find this in your documents. "
    "Nothing in the corpus covers it, so there is no grounded answer to give."
)
